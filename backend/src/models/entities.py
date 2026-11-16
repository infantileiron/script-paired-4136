from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True,nullable=False);password=Column(String(200));role=Column(String(20))
class Pair(Base):
 __tablename__='pairs'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);team=Column(String(40));before=Column(Float,nullable=True);after=Column(Float,nullable=True);note=Column(Text,default='')
class Evaluation(Base):
 __tablename__='evaluations'
 id=Column(Integer,primary_key=True);name=Column(String(100));team=Column(String(40));state=Column(String(20),default='queued');result=Column(JSON,nullable=True);error=Column(Text,default='')
class Adoption(Base):
 __tablename__='adoptions'
 id=Column(Integer,primary_key=True);evaluation_id=Column(Integer,ForeignKey('evaluations.id'));decision=Column(String(30));note=Column(Text);status=Column(String(20),default='draft')
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
class AnonRelease(Base):
 __tablename__='anon_releases'
 id=Column(Integer,primary_key=True)
 evaluation_id=Column(Integer,ForeignKey('evaluations.id'),nullable=False)
 name=Column(String(120),default='')
 state=Column(String(20),default='pending',nullable=False)
 # 固定评估名单：提交时冻结的顾问编号有序列表，后续重试不再重新选样
 roster=Column(JSON,nullable=False)
 lower=Column(Float,nullable=False);upper=Column(Float,nullable=False)
 epsilon=Column(Float,nullable=False)
 artifact_path=Column(String(300),default='')
 result=Column(JSON,nullable=True)
 error=Column(Text,default='')
 attempts=Column(Integer,default=0)
 created=Column(String(40));updated=Column(String(40))
class PrivacyBudget(Base):
 __tablename__='privacy_budgets'
 id=Column(Integer,primary_key=True)
 consultant_code=Column(String(60),unique=True,nullable=False)
 total_epsilon=Column(Float,nullable=False)
 spent_epsilon=Column(Float,default=0.0,nullable=False)
class PrivacyLedger(Base):
 __tablename__='privacy_ledger'
 id=Column(Integer,primary_key=True)
 release_id=Column(Integer,ForeignKey('anon_releases.id'),nullable=False)
 consultant_code=Column(String(60),nullable=False)
 epsilon=Column(Float,nullable=False)
 created=Column(String(40))
 __table_args__=(UniqueConstraint('release_id','consultant_code',name='uq_ledger_release_consultant'),)
