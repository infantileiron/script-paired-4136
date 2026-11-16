import random
from src.config.database import Base,engine,Session
from src.models.entities import User,Pair,PrivacyBudget
from src.services.privacy import TOTAL_EPSILON
from src.utils.security import hash_password
def seed():
 Base.metadata.create_all(engine);rng=random.Random(1115)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  for i in range(40):
   code=f'QY-{i+1:03}';before=round(rng.uniform(58,85),1);after=round(min(100,before+rng.gauss(4 if i<20 else 1,5)),1)
   if not s.query(Pair).filter_by(code=code).first():s.add(Pair(code=code,team='企业一组' if i<20 else '企业二组',before=None if i==38 else before,after=None if i==39 else after,note='前后各抽检5次客户沟通的平均得分；窗口均为7日'))
  s.commit()
  # 为每位顾问建立累计隐私预算账户（共享上限，跨组/跨评估发布统一扣账）
  codes=[p.code for p in s.query(Pair).order_by(Pair.code).all()]
  for code in codes:
   if not s.query(PrivacyBudget).filter_by(consultant_code=code).first():
    s.add(PrivacyBudget(consultant_code=code,total_epsilon=TOTAL_EPSILON,spent_epsilon=0.0))
  s.commit();print({'users':s.query(User).count(),'pairs':s.query(Pair).count(),'budgets':s.query(PrivacyBudget).count()})
if __name__=='__main__':seed()
