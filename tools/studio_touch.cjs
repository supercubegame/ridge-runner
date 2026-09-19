const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const results=[];
 try{
  for(const viewport of [{width:1280,height:720},{width:960,height:540}]){
   const context=await browser.newContext({viewport,hasTouch:true,isMobile:true,deviceScaleFactor:1});
   const page=await context.newPage();const errors=[];const checks=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(/SCRIPT ERROR:|Parse Error:/.test(m.text()))errors.push(m.text());});
   let stage='load';
   try{
    await page.goto(fs.readFileSync('out/preview-url.txt','utf8'),{waitUntil:'domcontentloaded',timeout:30000});
    await page.bringToFront();
    await page.waitForFunction(()=>window.__RIDGE?.floor===true,null,{timeout:90000});
    const cdp=await context.newCDPSession(page);
    const box=await page.locator('canvas').boundingBox();
    if(!box)throw Error('Canvas missing');
    const scale=Math.min(box.width/1280,box.height/720);
    const x0=box.x+(box.width-1280*scale)/2,y0=box.y+(box.height-720*scale)/2;
    const point=(x,y,id)=>({x:x0+x*scale,y:y0+y*scale,id,radiusX:3,radiusY:3,force:1});
    const forward=point(130,480,1),jump=point(1120,600,2);
    const send=(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points});
    const check=name=>checks.push({name,pass:true});
    const initial=await page.evaluate(()=>window.__RIDGE);
    stage='frames';await page.waitForFunction(n=>window.__RIDGE.frames>n+10,initial.frames,{timeout:15000});check('game advances frames with mobile touch context');
    stage='touch_forward';await send('touchStart',[forward]);
    await page.waitForFunction(z=>window.__RIDGE.z<z-0.4,initial.z,{timeout:5000});
    await send('touchEnd',[]);check('touch forward changes character position');
    stage='touch_release';await page.waitForTimeout(300);
    const stopped=await page.evaluate(()=>window.__RIDGE.z);await page.waitForTimeout(400);
    const after=await page.evaluate(()=>window.__RIDGE.z);
    if(Math.abs(after-stopped)>0.05)throw Error('Touch action remained pressed');check('releasing touch stops movement');
    stage='touch_jump';const y=await page.evaluate(()=>window.__RIDGE.y);
    await send('touchStart',[jump]);await page.waitForFunction(y=>window.__RIDGE.y>y+0.5,y,{timeout:5000});
    await send('touchEnd',[]);check('touch jump changes character elevation');
    await page.waitForFunction(()=>window.__RIDGE.floor,null,{timeout:10000});
    stage='touch_restart';const reset=point(1155,47,3);await page.touchscreen.tap(reset.x,reset.y);
    await page.waitForFunction(()=>Math.abs(window.__RIDGE.z)<0.1&&window.__RIDGE.falls===0,null,{timeout:5000});check('touch restart resets character');
    await page.waitForFunction(()=>window.__RIDGE.floor,null,{timeout:10000});
    stage='multitouch';const before=await page.evaluate(()=>window.__RIDGE);
    await send('touchStart',[forward]);await send('touchStart',[forward,jump]);
    await page.waitForFunction(s=>window.__RIDGE.z<s.z-0.3&&window.__RIDGE.y>s.y+0.4,before,{timeout:5000});
    await send('touchEnd',[]);check('simultaneous forward and jump work');
    stage='errors';if(errors.length)throw Error('Engine or JavaScript errors');check('no engine or JavaScript errors');
    await page.screenshot({path:`out/touch-${viewport.width}.png`});
    results.push({viewport,status:'PASS',checks});
   }catch(e){
    results.push({viewport,status:'FAIL',stage,checks,error:String(e).slice(0,700),errors:errors.slice(0,4)});
    await page.screenshot({path:`out/touch-failed-${viewport.width}.png`}).catch(()=>{});
   }finally{await context.close();}
  }
 }finally{await browser.close();}
 const status=results.length===2&&results.every(r=>r.status==='PASS')?'PASS':'FAIL';
 fs.writeFileSync('out/touch.json',JSON.stringify({status,results,coverage:'Chromium simulated touch, landscape only; not physical Android/iOS acceptance'},null,2));
 if(status!=='PASS')process.exit(1);
})().catch(e=>{fs.writeFileSync('out/touch.json',JSON.stringify({status:'FAIL',stage:'harness',error:String(e).slice(0,700)}));process.exit(1)});
