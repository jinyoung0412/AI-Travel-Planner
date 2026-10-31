from types import SimpleNamespace
import pytest
from scripts.api_test_budget import BudgetGuard,BudgetExceeded,MODEL

REQUEST=dict(model=MODEL,max_tokens=512,system='system',messages=[dict(role='user',content='카페')])
def response():return SimpleNamespace(usage=SimpleNamespace(input_tokens=100,output_tokens=20))
def test_usage_is_charged_and_reservation_released(tmp_path):
    guard=BudgetGuard(tmp_path)
    assert guard.send(lambda *a,**kw:response(),None,**REQUEST).usage.input_tokens==100
    assert guard.spent==pytest.approx(.0002) and guard.held==0

def test_cap_blocks_before_network_and_survives_restart(tmp_path):
    guard=BudgetGuard(tmp_path,limit_usd=.0001);calls=[]
    with pytest.raises(BudgetExceeded):guard.send(lambda *a,**kw:calls.append(1),None,**REQUEST)
    assert not calls and (tmp_path/'STOP').exists()

def test_unknown_usage_keeps_reservation(tmp_path):
    guard=BudgetGuard(tmp_path)
    def fail(*a,**kw):raise TimeoutError()
    with pytest.raises(TimeoutError):guard.send(fail,None,**REQUEST)
    assert guard.held>0 and guard.unknown==1
    again=BudgetGuard(tmp_path)
    assert again.held==pytest.approx(guard.held)

@pytest.mark.parametrize('changes',[dict(model='other'),dict(max_tokens=2400),dict(tools=[{}]),dict(system=[]),dict(messages=[dict(content=[])])])
def test_unpriced_features_are_rejected(tmp_path,changes):
    guard=BudgetGuard(tmp_path);calls=[]
    with pytest.raises(BudgetExceeded):guard.send(lambda *a,**kw:calls.append(1),None,**(REQUEST|changes))
    assert not calls


def test_reopening_a_ledger_cannot_raise_a_lowered_limit(tmp_path):
    original=BudgetGuard(tmp_path,limit_usd=2.8)
    original.send(lambda *a,**kw:response(),None,**REQUEST)
    reopened=BudgetGuard(tmp_path,limit_usd=3.5)
    assert reopened.limit==2.8
