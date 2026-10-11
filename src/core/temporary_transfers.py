"""识别暂估与正式往来的内部转科目；原发生额保留，账龄流量等额抵消。"""
from collections import defaultdict
import re
import pandas as pd
from src.core.current_accounts import CATEGORY_COLUMN,DIRECTION_COLUMN,BLANK_DETAIL,classify_current_account
from src.core.preflight import text
from src.core.fifo_engine import FIFOEngine

TRANSFER_COLUMNS=['单位','归集科目','暂估科目','正式科目','暂估日期','暂估凭证','正式日期','正式凭证','承接金额','匹配依据','暂估来源','正式来源']
ID_PATTERN=re.compile(r'(?<![A-Z0-9])(?:[A-Z]{1,12}-)?\d{4}-\d{2}-\d{2}-\d{3,8}\b|\b\d{20}\b',re.I)

def business_ids(value):
    return set(ID_PATTERN.findall(text(value)))

def voucher_key(row):
    source=text(row.get('来源文件')) or re.sub(r' 第\d+行$','',text(row.get('_来源工作表')))
    voucher=text(row.get('凭证号'))
    day=pd.to_datetime(row.get('日期'),errors='coerce')
    return (day.date() if pd.notna(day) else None,source,voucher)

def attach_business_ids(journal,aliases):
    """在过滤前读取同凭证业务单号；单据行优先，完整凭证可补库存行证据。"""
    result=journal.copy()
    if '_业务单号' not in result.columns:result['_业务单号']=''
    grouped=defaultdict(list)
    for index,row in result.iterrows():grouped[voucher_key(row)].append((index,row))
    for (_,_,voucher),items in grouped.items():
        parties={aliases.get(text(r.get('明细名称')),text(r.get('明细名称'))) for _,r in items
                 if classify_current_account(r.get('科目编码'),r.get('科目名称')).status=='retained'}-{BLANK_DETAIL,''}
        for index,row in items:
            own=business_ids(row.get('_业务单号'))|business_ids(row.get('摘要'))|business_ids(row.get('业务单号'))
            # 已有具体业务单号的行不混入同凭证其他采购批次。
            order_ids={x for x in own if '-' in x}
            unit=aliases.get(text(row.get('明细名称')),text(row.get('明细名称')))
            if voucher and not order_ids and unit in parties:
                for _,other in items:
                    content=text(other.get('摘要'))+' '+text(other.get('明细名称'))
                    mentioned={p for p in parties if p in content or any(a in content for a,b in aliases.items() if b==p)}
                    if unit in mentioned or (len(parties)==1 and not mentioned):
                        own |= business_ids(other.get('摘要'))|business_ids(other.get('业务单号'))
            result.at[index,'_业务单号']=' / '.join(sorted(own))
    return result

def mark_transfers(journal,cutoff):
    """仅同一已确认单位、同一归集科目的可证明对应业务参与抵消。"""
    result=journal.copy()
    result['_转科目借方']=0.0;result['_转科目贷方']=0.0
    grouped=defaultdict(list)
    for index,row in result.iterrows():
        day=pd.to_datetime(row.get('日期'),errors='coerce')
        if pd.isna(day) or day.date()>cutoff:continue
        if text(row.get('明细名称')) in ('',BLANK_DETAIL):continue
        normalized=FIFOEngine._normalize_amounts([{'debit':row.get('借方金额',0),'credit':row.get('贷方金额',0)}])[0]
        event={'index':index,'date':day.date(),'row':row,'ids':business_ids(row.get('_业务单号')),'debit':round(normalized['debit'],2),'credit':round(normalized['credit'],2)}
        grouped[(row['明细名称'],row[CATEGORY_COLUMN])].append(event)
    records=[]
    for (unit,category),events in grouped.items():
        temp=[e for e in events if e['row'].get('_是否暂估',False)]
        normal=[e for e in events if not e['row'].get('_是否暂估',False)]
        if not temp or not normal:continue
        increase='debit' if events[0]['row'][DIRECTION_COLUMN]=='debit' else 'credit'
        decrease='credit' if increase=='debit' else 'debit'
        for t in temp:
            summary=text(t['row'].get('摘要'))
            if re.search(r'退货|退回|退款|银行|现金|收款|付款|支付',summary):continue
            for n in sorted(normal,key=lambda e:abs((e['date']-t['date']).days)):
                ns=text(n['row'].get('摘要'))
                if re.search(r'退货|退回|退款|银行|现金|收款|付款|支付',ns):continue
                common=t['ids'] & n['ids']
                t_orders={x for x in t['ids'] if '-' in x}
                n_orders={x for x in n['ids'] if '-' in x}
                if t_orders and n_orders and not t_orders.intersection(n_orders):continue
                same_voucher=bool(text(t['row'].get('凭证号'))) and voucher_key(t['row'])==voucher_key(n['row'])
                explicit=bool(re.search(r'冲|结转|转入|转出|转科目|重分类|调整',summary))
                formal=bool(re.search(r'发票|开票|转入|转出|转科目|重分类|正式|结转',ns))
                evidence=('相同业务单号：'+' / '.join(sorted(common))) if common else ('同凭证冲暂估并正式入账' if same_voucher and explicit and formal else '')
                if not evidence:continue
                # 正向转正式；反向转暂估须有明确转科目语义，不能误认普通发票红冲。
                pairs=[(decrease,increase)]
                if re.search(r'转暂估|转入暂估|转科目|重分类',summary+' '+ns):pairs.append((increase,decrease))
                for tk,nk in pairs:
                    amount=round(min(t[tk],n[nk]),2)
                    if amount<=0:continue
                    t[tk]=round(t[tk]-amount,2);n[nk]=round(n[nk]-amount,2)
                    for event,column in [(t,tk),(n,nk)]:
                        marker='_转科目借方' if column=='debit' else '_转科目贷方'
                        result.at[event['index'],marker]+=amount
                    tr=t['row'];nr=n['row']
                    records.append({'单位':unit,'归集科目':category,'暂估科目':text(tr.get('_原科目编码'))+' '+text(tr.get('_原科目名称')),
                        '正式科目':text(nr.get('_原科目编码'))+' '+text(nr.get('_原科目名称')),'暂估日期':str(t['date']),'暂估凭证':text(tr.get('凭证号')),
                        '正式日期':str(n['date']),'正式凭证':text(nr.get('凭证号')),'承接金额':amount,'匹配依据':evidence,
                        '暂估来源':text(tr.get('_来源工作表')),'正式来源':text(nr.get('_来源工作表'))})
    return result,records
