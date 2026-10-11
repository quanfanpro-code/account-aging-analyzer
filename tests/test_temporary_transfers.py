from datetime import date
import pandas as pd
import pytest
from src.core.workflow import AgingWorkflow
from src.core.current_accounts import ACCOUNT_RULES
from src.core.report import ReportGenerator

def journal(rows):
    return pd.DataFrame(rows,columns=['日期','科目编码','科目名称','明细名称','借方金额','贷方金额','摘要','凭证号'])

def opening():
    return pd.DataFrame(columns=['科目编码','科目名称','明细名称','借方余额','贷方余额'])

@pytest.mark.parametrize('name,code,direction',ACCOUNT_RULES)
@pytest.mark.parametrize('nested',[False,True])
def test_八类往来各层级暂估转正式保留两批账龄和实际核销(name,code,direction,nested):
    tempcode=code+'02' if nested else '1999'
    tempname=name+'-暂估' if nested else '暂估'+name
    def amounts(increase):return (increase,0) if direction=='debit' else (0,increase)
    def decrease(amount):return (0,amount) if direction=='debit' else (amount,0)
    rows=[
        [date(2023,3,1),tempcode,tempname,'单位甲',*amounts(200),'业务/II-2023-03-01-0001','记-1'],
        [date(2025,2,1),tempcode,tempname,'单位甲',*amounts(100),'业务/II-2025-02-01-0002','记-2'],
        [date(2025,5,1),code,name,'单位甲',*decrease(60),'实际收付款','记-3'],
        [date(2025,8,1),tempcode,tempname,'单位甲',*decrease(100),'冲暂估/II-2023-03-01-0001','记-4'],
        [date(2025,8,1),code+'01',name+'-正式','单位甲',*amounts(100),'正式发票/II-2023-03-01-0001','记-5'],
        [date(2025,8,1),tempcode,tempname,'单位甲',*decrease(80),'冲暂估/II-2025-02-01-0002','记-6'],
        [date(2025,8,1),code+'01',name+'-正式','单位甲',*amounts(80),'正式发票/II-2025-02-01-0002','记-7'],
    ]
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    result=f.run(opening(),journal(rows),temporary_assignments={tempcode:name})
    assert len(result)==1 and result[0].closing_balance==240
    assert result[0].bucket_totals==[100,140]
    assert {e.source_date:e.amount for e in result[0].entries}=={date(2023,3,1):140,date(2025,2,1):100}
    assert all('II-' in e.source for e in result[0].entries)
    assert f.source_results[0].total_debit==pytest.approx(480 if direction=='debit' else 240)
    assert f.source_results[0].total_credit==pytest.approx(240 if direction=='debit' else 480)
    assert sum(r['承接金额'] for r in f.transfer_records)==180
    frames=dict(ReportGenerator().build_frames(result,{'buckets':[(0,365),(366,9999)],'transfer_records':f.transfer_records}))
    assert sum(frames['内部转科目记录']['承接金额'])==180

def test_同日不同业务和采购退货不冒认转科目():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购/II-2023-03-01-0001','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'采购退货/II-2023-03-01-0001','记-2'],
        [date(2025,8,1),'2202','应付账款','单位甲',0,100,'发票/II-2025-08-01-0002','记-2'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[100,100]
    assert f.transfer_records==[]

def test_红字部分转科目和正常付款金额不能互相吞掉():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',0,-100,'冲暂估','记-2'],
        [date(2025,8,1),'2202','应付账款','单位甲',0,113,'收到采购发票','记-2'],
        [date(2025,8,1),'2202','应付账款','单位甲',60,0,'银行付款','记-3'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].closing_balance==153 and r[0].bucket_totals==[13,140]
    assert f.transfer_records[0]['承接金额']==100

def test_截止日后的正式入账不能提前抵消暂估冲回():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,12,31),'1999','暂估应付款','单位甲',100,0,'冲暂估/II-2023-03-01-0001','记-2'],
        [date(2026,1,1),'2202','应付账款','单位甲',0,100,'发票/II-2023-03-01-0001','记-3'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].closing_balance==100 and r[0].bucket_totals==[0,100]
    assert f.transfer_records==[]

def test_同凭证不同批次不能因为金额相等认定转科目():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'冲暂估/II-2023-03-01-0001','记-2'],
        [date(2025,8,1),'2202','应付账款','单位甲',0,100,'发票/II-2025-08-01-0002','记-2'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[100,100]
    assert f.transfer_records==[]

def test_暂估分支的下级明细按同一个分支确认():
    j=journal([
        [date(2023,3,1),'22020201','应付账款-暂估材料-内销','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'22020201','应付账款-暂估材料-内销','单位甲',100,0,'冲暂估','记-2'],
        [date(2025,8,1),'220201','应付账款-正式','单位甲',0,100,'收到发票','记-2'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    pending=f.preflight(opening(),j)
    assert [(p.code,p.suggested) for p in pending.temporary]==[('220202','应付账款')]
    r=f.run(opening(),j,temporary_assignments={'220202':'应付账款'})
    assert r[0].bucket_totals==[0,200]

def test_跨凭证从库存行补业务单号保留原批次():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,1000,'采购/II-2023-03-01-0001','记-1'],
        [date(2025,7,1),'2202','应付账款','单位甲',500,0,'实际付款','记-2'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',0,-1000,'冲暂估/II-2023-03-01-0001','记-3'],
        [date(2025,8,1),'2202','应付账款','单位甲',0,1130,'收采购发票/12345678901234567890','记-4'],
        [date(2025,8,1),'1403','原材料','',1000,0,'采购/II-2023-03-01-0001/单位甲','记-4'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[130,500]
    assert len(f.journal_input)==4
    assert f.transfer_records[0]['承接金额']==1000
    assert 'II-2023-03-01-0001' in f.transfer_records[0]['匹配依据']

def test_相同单号但不同单位不互相承接():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,100,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'冲暂估/II-2023-03-01-0001','记-2'],
        [date(2025,8,1),'2202','应付账款','单位乙',0,100,'发票/II-2023-03-01-0001','记-2'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert [(x.detail_name,x.closing_balance,x.bucket_totals) for x in r]==[('单位乙',100,[100,0])]
    assert f.transfer_records==[]

def test_已提取完整凭证业务单号的明细表保留补充证据():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'冲暂估','记-2'],
        [date(2025,8,1),'2202','应付账款','单位甲',0,100,'收到发票','记-3'],
    ])
    j['_业务单号']=['','II-2023-03-01-0001','II-2023-03-01-0001']
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[0,200]
    assert len(f.transfer_records)==1

def test_同业务跨日期转科目也承接_截止日必须两边都入账():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'冲暂估/II-2023-03-01-0001','记-2'],
        [date(2025,8,2),'2202','应付账款','单位甲',0,100,'收到发票/II-2023-03-01-0001','记-3'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[0,200]
    assert f.transfer_records[0]['暂估日期']=='2025-08-01'
    assert f.transfer_records[0]['正式日期']=='2025-08-02'
    earlier=AgingWorkflow(date(2025,8,1),[(0,365),(366,9999)])
    r=earlier.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].closing_balance==100 and earlier.transfer_records==[]

def test_直接在暂估科目付款不能因相同采购单号当成转科目():
    j=journal([
        [date(2023,3,1),'1999','暂估应付款','单位甲',0,200,'采购','记-1'],
        [date(2025,8,1),'1999','暂估应付款','单位甲',100,0,'普通采购付款/II-2023-03-01-0001','记-2'],
        [date(2025,8,2),'2202','应付账款','单位甲',0,100,'收到发票/II-2023-03-01-0001','记-3'],
    ])
    f=AgingWorkflow(date(2025,12,31),[(0,365),(366,9999)])
    r=f.run(opening(),j,temporary_assignments={'1999':'应付账款'})
    assert r[0].bucket_totals==[100,100] and not f.transfer_records
