"""测试数据工厂：构造配对、完成的评估（带冻结快照）与预算账户。"""
from src.models.entities import Pair, Evaluation, PrivacyBudget
from src.services.privacy import TOTAL_EPSILON


def make_pair(s, code, team='企业一组', before=70.0, after=75.0, note=''):
    p = Pair(code=code, team=team, before=before, after=after, note=note)
    s.add(p)
    return p


def make_evaluation(s, name='评估', team='全部', state='done', pairs=None):
    """pairs: list[Pair]；快照冻结建表时刻的完整字段，模拟 worker 产出。"""
    rows = [{
        'code': p.code, 'team': p.team, 'before': p.before,
        'after': p.after, 'note': p.note,
    } for p in (pairs or [])]
    ev = Evaluation(name=name, team=team, state=state,
                    result={'snapshot': rows, 'n': len(rows)})
    s.add(ev)
    s.flush()
    return ev


def make_budgets(s, codes, total=TOTAL_EPSILON):
    for c in codes:
        s.add(PrivacyBudget(consultant_code=c, total_epsilon=total, spent_epsilon=0.0))


def spend(s, code, amount):
    from src.models.entities import PrivacyBudget
    row = s.query(PrivacyBudget).filter_by(consultant_code=code).one()
    row.spent_epsilon += amount
    return row
