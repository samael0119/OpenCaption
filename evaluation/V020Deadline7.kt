import dev.opencaption.opencaption.E2eSegmenter
import dev.opencaption.opencaption.E2eAudioQueue
import dev.opencaption.opencaption.E2eAudioChunk
import java.io.File

/** Evaluation-only candidate; deadline never slides after a pause. */
class AnchoredDeadline7 {
 private var start=0L;private var previous=0L;private var lastSpeech=0L
 private var heard=false;private var deadline=80000L
 fun update(total:Long,p:Double?):E2eSegmenter.Boundary? {
  require(total>=previous && total-previous<=320);previous=total
  val reliable=p?.takeIf{it.isFinite() && it in 0.0..1.0}
  if(reliable!=null && reliable>=.5){lastSpeech=total;heard=true}
  val reason=when {total>=deadline->"maximum";reliable!=null && heard && total-lastSpeech>=9600->"pause";else->return null}
  if(total>=deadline){check(total==deadline);deadline+=80000}
  return emit(total,reason)
 }
 fun flush(total:Long):E2eSegmenter.Boundary?=if(total>start)emit(total,"tail")else null
 private fun emit(end:Long,reason:String):E2eSegmenter.Boundary {
  check(end>start && end-start<=80000)
  return E2eSegmenter.Boundary(start,end,reason).also{start=end;heard=false}
 }
}
object V020Deadline7 {
 @JvmStatic fun main(args:Array<String>) {
  val out=File(args[0]);val all=File(out,"frames.tsv").readLines().map{it.split('\t')}.groupBy{it[0]}
  File(out,"product.tsv").bufferedWriter().use {log ->
   for((name,fs) in all)for(policy in listOf("baseline","anchored")) {
    val base=E2eSegmenter();val candidate=AnchoredDeadline7();val ws=mutableListOf<E2eSegmenter.Boundary>()
    for(f in fs){val t=f[1].toLong();val p=when(f[2]){"null"->null;"nan"->Double.NaN;else->f[2].toDouble()};(if(policy=="baseline")base.update(t,p)else candidate.update(t,p))?.let{ws.add(it)}}
    (if(policy=="baseline")base.flush(fs.last()[1].toLong())else candidate.flush(fs.last()[1].toLong()))?.let{ws.add(it)}
    check(ws.first().start==0L && ws.last().end==fs.last()[1].toLong());check(ws.zipWithNext().all{it.first.end==it.second.start});check(ws.all{it.end>it.start && it.end-it.start<=80000})
    for(w in ws)log.appendLine("segment\t$name\t$policy\t${w.start}\t${w.end}\t${w.reason}")
    if(name.startsWith("test"))continue
    for(cost in listOf(1000L,2000L,3000L,4000L)) {
     val q=E2eAudioQueue();q.reset(1);var running:E2eAudioChunk?=null;var done=0L
     fun record(c:E2eAudioChunk,kind:String,at:Long){log.appendLine("queue\t$name\t$policy\t$cost\t$kind\t${c.startMs}\t${c.endMs}\t$at")}
     fun take(now:Long){val a=q.take(1,now);a.expired?.let{record(it,"expired",now)};running=a.chunk;if(running!=null)done=now+cost else q.finish(1)}
     fun complete(){record(running!!,"delivered",done);running=null;if(q.finish(1))take(done)}
     for((id,w) in ws.withIndex()) {
      val now=w.end/16;while(running!=null && done<=now)complete()
      val r=q.offer(E2eAudioChunk(1,id.toLong(),w.start/16,w.end/16,FloatArray((w.end-w.start).toInt()),now))
      r.dropped?.let{record(it,"replaced",now)};if(r.schedule)take(now);check(q.pendingCount()<=1)
     }
     while(running!=null)complete();check(q.pendingCount()==0)
    }
   }
  }
  println("Deadline candidate/baseline:16 shifted real traces +12 mechanisms; no model")
 }
}
