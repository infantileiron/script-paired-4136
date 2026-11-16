import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Pair,Evaluation,Adoption,Audit,AnonRelease
from src.schemas.business import Login,PairInput,EvaluationInput,AdoptionInput,ReleaseInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.broker import RELEASE_QUEUE,broker
from src.services import privacy,publish as publish_service
from src.controllers.business import ensure_evaluation
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/pairs')
def pairs(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Pair).order_by(Pair.id).all()]
@router.post('/pairs')
def create_pair(data:PairInput,u=Depends(editor),s=Depends(db)):
 r=Pair(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'顾问编号已存在，每位顾问仅保留一组前后测')
 audit(s,u,'录入顾问配对 '+r.code);return dump(r)
@router.put('/pairs/{i}')
def edit_pair(i:int,data:PairInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Pair,i)
 if not r:raise HTTPException(404,'配对记录不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'顾问编号重复')
 audit(s,u,'修订配对 '+str(i));return dump(r)
@router.get('/evaluations')
def evaluations(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Evaluation).order_by(Evaluation.id.desc()).all()]
@router.post('/evaluations')
def evaluate(data:EvaluationInput,u=Depends(editor),s=Depends(db)):
 rows=[dump(r) for r in s.query(Pair).order_by(Pair.id).all() if data.team=='全部' or r.team==data.team]
 r=Evaluation(**data.model_dump(),result={'snapshot':rows});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('paired:evaluations',r.id)
 except redis.RedisError:r.state='failed';r.error='队列暂不可用，请稍后重新提交';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交评估 '+str(r.id));return dump(r)
@router.get('/evaluations/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_evaluation(s,i))
@router.get('/evaluations/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_evaluation(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功评估可导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="script-paired-{i}.json"'})
@router.get('/adoptions')
def adoptions(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Adoption).order_by(Adoption.id.desc()).all()]
@router.post('/adoptions')
def adoption(data:AdoptionInput,u=Depends(editor),s=Depends(db)):
 if ensure_evaluation(s,data.evaluation_id).state!='done':raise HTTPException(409,'评估完成后才能起草采纳意见')
 r=Adoption(**data.model_dump());s.add(r);s.commit();audit(s,u,'起草采纳意见 '+str(r.id));return dump(r)
@router.post('/adoptions/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=s.get(Adoption,i)
 if not r:raise HTTPException(404,'采纳意见不存在')
 if r.status!='draft':raise HTTPException(409,'已签核意见不可重复签核')
 r.status='approved';s.commit();audit(s,u,'签核意见 '+str(i));return dump(r)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
# ---- 差分隐私匿名发布 ----
@router.get('/releases/budget')
def release_budget(u=Depends(current),s=Depends(db)):
 """页面查询每位顾问的累计隐私预算与全部发布申请状态。"""
 return publish_service.budget_overview(s)
@router.get('/releases')
def releases(u=Depends(current),s=Depends(db)):
 return [dump(r) for r in s.query(AnonRelease).order_by(AnonRelease.id.desc()).all()]
@router.post('/releases')
def create_release(data:ReleaseInput,u=Depends(editor),s=Depends(db)):
 """提交匿名发布：固定评估名单，校验裁剪界与预算可行性后入队，由 worker 异步加噪。"""
 try:data.check_bounds()
 except ValueError as e:raise HTTPException(422,str(e))
 try:ev,codes=publish_service.fixed_roster(s,data.evaluation_id)
 except LookupError:raise HTTPException(404,'评估任务不存在')
 except ValueError as e:raise HTTPException(409,str(e))
 # 预建预算账户，并在入队前做一次预检（最终扣账在 worker 事务内，并发以锁+行锁为准）
 accounts=publish_service.ensure_budget_accounts(s,codes)
 insufficient=sorted(c for c in codes
   if accounts[c].spent_epsilon+data.epsilon>privacy.TOTAL_EPSILON+1e-12)
 if insufficient:raise HTTPException(402,'隐私预算不足，整次拒绝：顾问 '+'、'.join(insufficient))
 r=AnonRelease(evaluation_id=ev.id,name=data.name or ('匿名发布-评估'+str(ev.id)),
   state='pending',roster=codes,lower=data.lower,upper=data.upper,epsilon=data.epsilon,
   attempts=0,created=publish_service.now_iso(),updated=publish_service.now_iso())
 s.add(r);s.commit()
 try:broker().rpush(RELEASE_QUEUE,r.id)
 except Exception:
  # 队列故障不允许产生永远 pending 的申请：标记失败，未扣任何预算
  r.state='failed';r.error='队列暂不可用，请稍后重新提交';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交匿名发布 '+str(r.id)+' 名单'+str(len(codes))+'人')
 return dump(r)
@router.get('/releases/{i}')
def release_detail(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(AnonRelease,i)
 if not r:raise HTTPException(404,'匿名发布申请不存在')
 return dump(r)
@router.get('/releases/{i}/download')
def release_download(i:int,u=Depends(current),s=Depends(db)):
 """仅当产物可下载时返回对外 JSON；下载可见即已扣账。内部原报告不在其中。"""
 r=s.get(AnonRelease,i)
 if not r:raise HTTPException(404,'匿名发布申请不存在')
 if r.state!='downloadable' or not r.result:
  raise HTTPException(409,'发布尚未完成或已失败，暂不可下载')
 payload=dict(r.result)
 return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',
  headers={'Content-Disposition':f'attachment; filename="anon-release-{i}.json"'})
@router.post('/releases/{i}/retry')
def release_retry(i:int,u=Depends(editor),s=Depends(db)):
 """失败/待处理申请重试：复用原申请与确定性噪声，不重扣预算。"""
 r=s.get(AnonRelease,i)
 if not r:raise HTTPException(404,'匿名发布申请不存在')
 if r.state=='downloadable':raise HTTPException(409,'发布已可下载，无需重试')
 r.state='pending';r.updated=publish_service.now_iso();s.commit()
 try:broker().rpush(RELEASE_QUEUE,r.id)
 except Exception:raise HTTPException(503,'队列暂不可用，请稍后重试')
 audit(s,u,'重试匿名发布 '+str(i))
 return dump(r)
