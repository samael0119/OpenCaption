import dev.opencaption.opencaption.E2eSegmenter
import dev.opencaption.opencaption.E2eAudioQueue
import dev.opencaption.opencaption.E2eAudioChunk
import java.io.File

object V020Latency7 {
 data class W(val start:Long,val end:Long,val reason:String)
 @JvmStatic fun main(args:Array<String>) {
  val out=File(args[0]); val all=File(out,"frames.tsv").readLines().filter{it.isNotBlank()}.map{it.split('\t')}.groupBy{it[0]}
  File(out,"product.tsv").bufferedWriter().use { log ->
   for ((name,fs) in all) for (ms in listOf(400L,600L)) {
    val s=E2eSegmenter(ms*16);val ws=mutableListOf<W>()
    for(f in fs) {val t=f[1].toLong();val p=when(f[2]){"null"->null;"nan"->Double.NaN;else->f[2].toDouble()};s.update(t,p)?.let{ws.add(W(it.start,it.end,it.reason))}}
    s.flush(fs.last()[1].toLong())?.let{ws.add(W(it.start,it.end,it.reason))}
    check(ws.first().start==0L && ws.last().end==fs.last()[1].toLong());check(ws.zipWithNext().all{it.first.end==it.second.start});check(ws.all{it.end>it.start && it.end-it.start<=80000})
    for(w in ws)log.appendLine("segment\t$name\t$ms\t${w.start}\t${w.end}\t${w.reason}")
    if(name.startsWith("test"))continue
    for(cost in listOf(1000L,2000L,3000L,4000L)) {
     val q=E2eAudioQueue();q.reset(1)
     var running:E2eAudioChunk?=null;var done=0L
     fun record(c:E2eAudioChunk,kind:String,at:Long){log.appendLine("queue\t$name\t$ms\t$cost\t$kind\t${c.startMs}\t${c.endMs}\t$at")}
     fun take(now:Long){val a=q.take(1,now);a.expired?.let{record(it,"expired",now)};running=a.chunk;if(running!=null)done=now+cost else q.finish(1)}
     fun complete(){val c=running!!;record(c,"delivered",done);running=null;if(q.finish(1))take(done)}
     for((id,w) in ws.withIndex()) {
      val now=w.end/16
      while(running!=null && done<=now)complete()
      val c=E2eAudioChunk(1,id.toLong(),w.start/16,w.end/16,FloatArray((w.end-w.start).toInt()),now)
      val r=q.offer(c);r.dropped?.let{record(it,"replaced",now)};if(r.schedule)take(now)
      check(q.pendingCount()<=1)
     }
     while(running!=null)complete()
     check(q.pendingCount()==0)
    }
   }
  }
  println("Product segmenter + queue replay complete; 4 real traces,12 mechanisms; zero model")
 }
}
