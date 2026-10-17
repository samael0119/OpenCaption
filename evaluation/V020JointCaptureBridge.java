import dev.opencaption.opencaption.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import javax.sound.sampled.*;

/** Local PCM clock adapter. Uses product VAD/segmenter/buffer/queue/input/cadence.
 * Android AudioRecord, Handler, watchdog and device scheduling are not simulated.
 * A pump waits for the actual model + Dart/widget acknowledgement while capture
 * continues; it never substitutes a measured duration or advances virtual time.
 */
public final class V020JointCaptureBridge {
  static final E2eAudioQueue queue = new E2eAudioQueue(80000, 5000);
  static final Semaphore scheduled = new Semaphore(0), acknowledged = new Semaphore(0);
  static volatile boolean captured = false;
  record Hints(String text, boolean automatic) {}
  static volatile Hints hints = new Hints("CS2 broadcast.", true);
  static long origin, index = 0;
  static long clock() { return (System.nanoTime()-origin)/1000000; }
  static String b64(String s) { return Base64.getEncoder().encodeToString(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
  static synchronized void emit(String s) { System.out.println(s); System.out.flush(); }
  static void gap(E2eAudioChunk c, String reason) { if(c != null) emit("GAP\t"+c.getWindow()+"\t"+c.getStartMs()+"\t"+c.getEndMs()+"\t"+reason); }
  static void wav(Path path, float[] pcm) throws Exception {
    byte[] bytes=new byte[pcm.length*2];
    for(int i=0;i<pcm.length;i++) { int n=Math.round(pcm[i]*32768f); bytes[2*i]=(byte)n; bytes[2*i+1]=(byte)(n>>8); }
    try(var stream=new AudioInputStream(new ByteArrayInputStream(bytes),new AudioFormat(16000,16,1,true,false),pcm.length)) {
      AudioSystem.write(stream,AudioFileFormat.Type.WAVE,path.toFile());
    }
  }
  public static void main(String[] args) throws Exception {
    Path root=Path.of(args[0]), source=Path.of(args[1]), input=Path.of(args[2]);
    int seconds=Integer.parseInt(args[3]);
    if(seconds<1 || seconds>3600) throw new IllegalArgumentException("bounded duration");
    float[] cycle;
    try(var stream=AudioSystem.getAudioInputStream(source.toFile())) {
      var f=stream.getFormat();
      if(f.getSampleRate()!=16000 || f.getChannels()!=1 || f.getSampleSizeInBits()!=16 || f.isBigEndian()) throw new IllegalArgumentException("PCM format");
      byte[] bytes=stream.readAllBytes();
      if(bytes.length==0 || bytes.length>16000*2*300) throw new IllegalArgumentException("playlist bound");
      cycle=new float[bytes.length/2];
      for(int i=0;i<cycle.length;i++) cycle[i]=(short)((bytes[2*i]&255)|(bytes[2*i+1]<<8))/32768f;
    }
    queue.reset(1);
    var reader=new BufferedReader(new InputStreamReader(System.in));
    // Python loads its single model first, then Dart starts the capture clock.
    if(!"BEGIN".equals(reader.readLine())) throw new IllegalStateException("BEGIN required");
    origin=System.nanoTime();
    Thread commands=new Thread(()-> {
      try {
        for(String line;(line=reader.readLine())!=null;) {
          String[] fields=line.split("\t",-1);
          if(fields[0].equals("ACK")) acknowledged.release();
          else if(fields[0].equals("HINT")) hints=new Hints(new String(Base64.getDecoder().decode(fields[1]),java.nio.charset.StandardCharsets.UTF_8),Boolean.parseBoolean(fields[2]));
          else throw new IllegalArgumentException("unknown command");
        }
      } catch(Exception e) { emit("ERR\t"+b64(e.toString())); System.exit(2); }
    },"local-command"); commands.setDaemon(true); commands.start();
    Thread pump=new Thread(()-> {
      try {
        while(true) {
          scheduled.acquire();
          while(true) {
            var take=queue.take(1,clock()); gap(take.getExpired(),"expired");
            var c=take.getChunk();
            if(c!=null) {
              boolean zero=true; for(float v:c.getPcm()) if(v!=0f) {zero=false;break;}
              if(zero) emit("ZERO\t"+c.getWindow()+"\t"+c.getStartMs()+"\t"+c.getEndMs());
              else {
                float[] prepared=E2eAudioInput.INSTANCE.prepareShort(c.getPcm()); wav(input,prepared);
                var h=hints;
                var chosen=E2eHintPolicy.INSTANCE.choose(++index,h.text(),h.automatic());
                emit("REQ\t"+c.getWindow()+"\t"+c.getStartMs()+"\t"+c.getEndMs()+"\t"+clock()+"\t"+c.getSubmittedAt()+"\t"+c.getPcm().length+"\t"+prepared.length+"\t"+b64(chosen.getHints())+"\t"+chosen.getVerification());
                if(!acknowledged.tryAcquire(120,TimeUnit.SECONDS)) throw new IllegalStateException("model/controller acknowledgement timeout");
              }
            }
            if(!queue.finish(1)) break;
          }
          if(captured && queue.pendingCount()==0) break;
        }
        emit("END\t"+clock()+"\t"+index);
      } catch(Exception e) { emit("ERR\t"+b64(e.toString())); System.exit(2); }
    },"local-pump"); pump.start();
    try(var vad=new SileroBoundaryVad(Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx")))) {
      var buffer=new AudioBuffer(160000); var segmenter=new E2eSegmenter(9600,80000);
      long window=0, maxLateNs=0; int frames=seconds*50;
      for(int frame=0;frame<frames;frame++) {
        long target=origin+(frame+1)*20000000L, left=target-System.nanoTime();
        if(left>0) TimeUnit.NANOSECONDS.sleep(left);
        long late=Math.max(0,System.nanoTime()-target); maxLateNs=Math.max(late,maxLateNs);
        if(late>1000000000L) throw new IllegalStateException("capture clock more than 1s late");
        float[] pcm=new float[320];
        for(int j=0;j<320;j++) pcm[j]=cycle[(frame*320+j)%cycle.length];
        buffer.append(pcm);
        var boundary=segmenter.update(buffer.getTotal(),vad.observe(pcm));
        if(boundary!=null) {
          var c=new E2eAudioChunk(1,++window,boundary.getStart()/16,boundary.getEnd()/16,buffer.slice(boundary.getStart(),boundary.getEnd()),clock());
          var offered=queue.offer(c); gap(offered.getDropped(),"replaced");
          emit("OFFER\t"+window+"\t"+c.getStartMs()+"\t"+c.getEndMs()+"\t"+boundary.getReason()+"\t"+offered.getMerged()+"\t"+queue.pendingCount());
          if(offered.getSchedule()) scheduled.release();
        }
        if(frame%50==49) emit("ACT\t"+buffer.getTotal()/16+"\t"+clock());
      }
      var tail=segmenter.flush(buffer.getTotal());
      if(tail!=null) {
        var c=new E2eAudioChunk(1,++window,tail.getStart()/16,tail.getEnd()/16,buffer.slice(tail.getStart(),tail.getEnd()),clock());
        var offer=queue.offer(c); gap(offer.getDropped(),"replaced");
        emit("OFFER\t"+window+"\t"+c.getStartMs()+"\t"+c.getEndMs()+"\ttail\t"+offer.getMerged()+"\t"+queue.pendingCount());
        if(offer.getSchedule()) scheduled.release();
      }
      emit("CAPEND\t"+seconds*1000+"\t"+frames+"\t"+maxLateNs/1000000.0+"\t"+clock());
      captured=true; scheduled.release();
    } catch(Exception e) { emit("ERR\t"+b64(e.toString())); System.exit(2); }
    pump.join(150000);
    if(pump.isAlive()) throw new IllegalStateException("pump did not drain");
  }
}
