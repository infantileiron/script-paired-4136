import os,time,json,logging
from pathlib import Path
from src.config.database import Session
from src.models.entities import Evaluation
from src.services.analysis import evaluate
from src.services.broker import broker,EVAL_QUEUE,RELEASE_QUEUE
from src.services import publish as publish_service

b=broker()

def _recover():
 """启动恢复：评估任务重置 queued 重新入队；匿名发布按产物状态恢复或重排队。"""
 with Session() as recovery:
  for pending in recovery.query(Evaluation).filter(Evaluation.state.in_(['queued','running'])).all():
   pending.state='queued';b.rpush(EVAL_QUEUE,pending.id)
  recovery.commit()
  publish_service.recover_pending(recovery)

def _handle_evaluation(item_id):
 with Session() as s:
  row=s.get(Evaluation,int(item_id))
  if not row or row.state!='queued':return
  snapshot=row.result['snapshot'];row.state='running';s.commit()
  try:
   row.result={**evaluate(snapshot),'snapshot':snapshot};row.state='done'
   Path(os.path.join(os.environ.get('ARTIFACT_DIR','/artifacts'),str(row.id)+'.json')).write_text(
    json.dumps(row.result,ensure_ascii=False))
  except Exception as e:
   row.state='failed';row.error=str(e)
  s.commit()

def _handle_release(item_id):
 with Session() as s:
  publish_service.process_release(s,int(item_id))

def main():
 _recover()
 while True:
  Path('/tmp/heartbeat').touch()
  try:
   # 优先处理匿名发布（预算扣账链路），再处理常规评估
   item=b.blpop(RELEASE_QUEUE,timeout=1)
   if item:
    _handle_release(item[1]);continue
   item=b.blpop(EVAL_QUEUE,timeout=3)
   if not item:continue
   _handle_evaluation(item[1])
  except Exception:
   logging.exception('worker');time.sleep(2)

if __name__=='__main__':
 main()
