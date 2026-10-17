// Local evaluation only. Queued telemetry is independent of inference scheduling.
(() => {
  const rows = [], pending = [];
  let handler = null, clock = null;
  function log(row) {
    const now = performance.now();
    const value = {...row, run_id:new URLSearchParams(location.search).get('run') || 'initial', browser_ms: now, visibility: document.visibilityState};
    if (clock) Object.assign(value, {clock_offset_min_ms:clock.min,clock_offset_max_ms:clock.max,
      server_time_min_ms:now+clock.min,server_time_max_ms:now+clock.max});
    rows.push(value);
    if (rows.length > 2000) rows.shift();
    fetch('/telemetry', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}).catch(()=>{});
  }
  async function sync() {
    let best=null;
    for(let i=0;i<5;i++) {
      const a=performance.now();const s=await fetch('/clock',{cache:'no-store'}).then(r=>r.json());const b=performance.now();
      const v={min:s.server_ms-b,max:s.server_ms-a,rtt:b-a};if(!best || v.rtt<best.rtt)best=v;
    }
    clock=best;log({type:'clock_sync',...best});return best;
  }
  function dispatch(event) {
    if(!handler){if(pending.length<128)pending.push(event);return;}
    log({type:'event_received',event_id:event.id,server_sent_ms:event.server_sent_ms});
    try {log(JSON.parse(handler(JSON.stringify(event))));}
    catch(e){log({type:'handler_error',message:String(e),event_id:event.id});}
  }
  const stream=new EventSource('/events');stream.onmessage=e=>dispatch(JSON.parse(e.data));
  stream.onerror=()=>log({type:'transport_error'});
  window.deliveryBridge={
    rows, sync,
    install(fn){handler=fn;log({type:'installed'});while(pending.length)dispatch(pending.shift());},
    frame(json){const row=JSON.parse(json);log({...row,type:'framework_frame'});
      requestAnimationFrame(a=>requestAnimationFrame(b=>log({...row,type:'browser_frame_bound',raf_first_ms:a,raf_second_ms:b,
      measurement:'framework layout followed by two browser frame opportunities; physical scanout not measured'})));},
    log(json){log(JSON.parse(json));},
    stop(){stream.close();log({type:'transport_closed'});},
  };
  document.addEventListener('visibilitychange',()=>log({type:'visibility_change'}));
  sync().catch(e=>log({type:'clock_error',message:String(e)}));
})();
