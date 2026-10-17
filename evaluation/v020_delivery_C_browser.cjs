// One bounded headful Chromium run on an explicit Xvfb virtual display.
const fs=require('fs'), path=require('path');
const {chromium}=require('/home/hyh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve('evaluation/results/v020-delivery/C');
const fixture=JSON.parse(fs.readFileSync(path.resolve('evaluation/results/v020-delivery/A/cache_fixture.json'))).rows;
const checks=[];const note=(name,passed,details={})=>checks.push({name,passed,...details});
async function main(){
 const browser=await chromium.launch({headless:false,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage','--disable-background-timer-throttling']});
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const send=async row=>{const r=await fetch('http://127.0.0.1:8766/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(!r.ok)throw Error('server '+r.status);};
 const wait=async (id,type)=>page.waitForFunction(([id,type])=>window.deliveryBridge?.rows.some(r=>r.event_id===id&&r.type===type),[id,type],{timeout:10000});
 const rows=()=>page.evaluate(()=>window.deliveryBridge.rows);
 const subtitle=(id,window,index=0,extra={})=>({type:'subtitle',id,window,start_ms:window*5000,end_ms:(window+1)*5000,english:fixture[index].english,chinese:fixture[index].chinese,...extra});
 try{
  await page.goto('http://127.0.0.1:8766/?theme=dark&run=font-fixed');
  await page.waitForFunction(()=>window.deliveryBridge?.rows.some(r=>r.type==='installed'),null,{timeout:30000});
  const sync=await page.evaluate(()=>window.deliveryBridge.sync());
  note('clock_interval',Number.isFinite(sync.min)&&sync.max>=sync.min&&sync.rtt<200,{rtt_ms:sync.rtt,offset_width_ms:sync.max-sync.min});
  await send(subtitle('desktop-cache',10));await wait('desktop-cache','browser_frame_bound');
  await page.waitForFunction(()=>window.deliveryBridge.rows.some(r=>r.event_id==='desktop-cache'&&r.type==='browser_frame_bound'&&r.fully_in_viewport),null,{timeout:10000});
  note('desktop_real_cache_frame',true);
  await page.screenshot({path:path.join(out,'desktop-dark.png')});
  await send(subtitle('duplicate',10));await wait('duplicate','not_delivered');note('duplicate_window',true);
  await send(subtitle('invalid',11,0,{end_ms:0}));await wait('invalid','invalid_event');note('invalid_interval',true);
  await send({id:'none-control',type:'no_speech'});await wait('none-control','no_subtitle_control');note('no_subtitle_transport_control',true,{native_parser_test:false});
  await send(subtitle('later',12,2));await wait('later','browser_frame_bound');
  await send(subtitle('out-of-order',11,1));await wait('out-of-order','browser_frame_bound');
  await page.screenshot({path:path.join(out,'desktop-dark.png')});
  const beforeMobile=await rows();const d=beforeMobile.find(r=>r.event_id==='out-of-order'&&r.type==='controller_delivered');
  const b=beforeMobile.find(r=>r.event_id==='out-of-order'&&r.type==='browser_frame_bound');
  note('out_of_order_caption_binding',Boolean(d&&b&&d.caption_id===b.caption_id&&d.chinese===b.caption_chinese));
  await page.setViewportSize({width:390,height:780});
  await send({id:'light',type:'theme',value:'light'});await wait('light','theme_changed');
  await send(subtitle('mobile-cache',13,6));await wait('mobile-cache','browser_frame_bound');
  await page.waitForFunction(()=>window.deliveryBridge.rows.some(r=>r.event_id==='mobile-cache'&&r.type==='browser_frame_bound'&&r.fully_in_viewport),null,{timeout:10000});
  await page.screenshot({path:path.join(out,'mobile-light.png')});note('mobile_light_cache_frame',true);
  const other=await context.newPage();await other.goto('about:blank');await other.bringToFront();
  let hidden=false;try{await page.waitForFunction(()=>document.visibilityState==='hidden',null,{timeout:2000});hidden=true;}catch{}
  if(hidden){await send(subtitle('hidden-cache',14,3));await wait('hidden-cache','controller_delivered');const h=await rows();note('hidden_page_not_eligible',h.filter(r=>r.event_id==='hidden-cache'&&r.type==='event_received').every(r=>r.visibility==='hidden'));}
  else note('hidden_page_not_eligible',null,{reason:'virtual display did not expose hidden lifecycle; not simulated'});
  await other.close();await page.bringToFront();
  // A long synthetic transport stress case, never audio or semantic evidence.
  await send(subtitle('long-layout',15,6,{chinese:fixture[6].chinese.repeat(12)}));await wait('long-layout','browser_frame_bound');
  await page.waitForFunction(()=>window.deliveryBridge.rows.filter(r=>r.event_id==='long-layout'&&r.type==='framework_frame').some(r=>r.elapsed_since_controller_ms>=1400),null,{timeout:5000});
  const long=(await rows()).filter(r=>r.event_id==='long-layout'&&r.type==='framework_frame');
  note('long_text_not_falsely_fully_visible',long.length>0&&long.every(r=>!r.fully_in_viewport),{synthetic_layout_only:true});
  await page.mouse.move(170,350);await page.mouse.wheel(0,-2000);await page.waitForTimeout(250);
  await send(subtitle('review-cache',16,2));await wait('review-cache','browser_frame_bound');
  await page.waitForFunction(()=>window.deliveryBridge.rows.filter(r=>r.event_id==='review-cache'&&r.type==='framework_frame').some(r=>r.elapsed_since_controller_ms>=1400 || r.fully_in_viewport),null,{timeout:5000});
  const review=(await rows()).filter(r=>r.event_id==='review-cache'&&r.type==='framework_frame');
  note('review_offscreen_not_visible',review.length>0&&review.every(r=>!r.visible_in_viewport),{native_wheel_scroll:true});
  await page.screenshot({path:path.join(out,'review-position.png')});
  await send({id:'end',type:'end'});await wait('end','ended');
  await send(subtitle('after-end',17));await wait('after-end','not_delivered');note('end_rejects_future_caption',true);
  await page.evaluate(()=>window.deliveryBridge.stop());
  note('transport_close', (await rows()).some(r=>r.type==='transport_closed'));
  fs.writeFileSync(path.join(out,'browser_rows.json'),JSON.stringify(await rows(),null,2));
  fs.writeFileSync(path.join(out,'browser_checks.json'),JSON.stringify({display:'Xvfb headful Chromium virtual display; physical screen scanout not measured',model_requests:0,checks,errors},null,2));
  console.log(JSON.stringify({checks:checks.length,passed:checks.filter(r=>r.passed===true).length,failed:checks.filter(r=>r.passed===false).length,untested:checks.filter(r=>r.passed===null).length,errors}));
 }finally{await context.close();await browser.close();}
}
main().catch(e=>{fs.writeFileSync(path.join(out,'browser_failure.json'),JSON.stringify({error:String(e),checks},null,2));console.error(e);process.exitCode=1;});
