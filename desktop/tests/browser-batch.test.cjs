'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {createBatch}=require('../browser-batch.cjs');
function harness(posts,pages){
 let page=0,loads=0;const saved=[],completed=[],outcomes=[];
 const io={persist:()=>{},delay:async()=>{},load:async()=>{page=0;loads++},inspect:async()=>pages[page],advance:async()=>{page++;return true},save:async(c,ctx)=>{saved.push(ctx);return {id:'file'+saved.length}},complete:async(...a)=>completed.push(a),outcome:async(...a)=>outcomes.push(a)};
 const batch=createBatch(io);batch.set(posts);return {batch,io,saved,completed,outcomes,loads:()=>loads};
}
const media=(signature,hasNext=false)=>({signature,hasNext,items:[{}],media:[{}],uploader:'author'});
test('carousel finishes before retiring failed root and saves exact requested child slots',async()=>{
 const h=harness([{url:'root',targets:[{id:'root',index:null,status:'failed'}]},{url:'child',targets:[{id:'child',index:1,status:'failed'}]}],[media('a',true),media('b')]);
 await h.batch.run();assert.equal(h.saved.length,3);assert.deepEqual(h.completed,[['root',['file1','file2']]]);assert.equal(h.saved[2].targetId,'child');assert.equal(h.saved[2].index,1);assert.equal(h.batch.get().status,'completed');
});
test('login pauses at current post and resumes without skipping it',async()=>{
 const pages=[{login:true,items:[]}];const h=harness([{url:'a',targets:[{id:'a',index:null,status:'failed'}]}],pages);
 await h.batch.run();assert.equal(h.batch.get().cursor,0);assert.equal(h.batch.get().status,'paused');assert.equal(h.saved.length,0);
 pages[0]=media('a');await h.batch.run();assert.equal(h.loads(),2);assert.equal(h.saved.length,1);assert.equal(h.batch.get().status,'completed');
});
test('metadata refresh for completed files never downloads or finalizes again',async()=>{
 const h=harness([{url:'a',targets:[{id:'a',index:null,status:'completed'}]}],[media('a')]);
 await h.batch.run();assert.equal(h.saved.length,0);assert.equal(h.completed.length,0);assert.equal(h.batch.get().results[0].metadataOnly,true);
});
test('failed carousel leaves original unresolved and runtime errors pause safely',async()=>{
 const h=harness([{url:'a',targets:[{id:'a',index:null,status:'failed'}]}],[media('a',true)]);h.io.advance=async()=>false;
 await h.batch.run();assert.equal(h.saved.length,1);assert.equal(h.completed.length,0);assert.equal(h.outcomes.length,1);assert.equal(h.batch.get().results[0].status,'review');
 const broken=harness([{url:'a',targets:[{id:'a',index:null,status:'failed'}]}],[{restricted:true,items:[]}]);broken.io.outcome=async()=>{throw Error('offline')};await broken.batch.run();assert.equal(broken.batch.get().status,'paused');assert.equal(broken.batch.get().running,false);
});
