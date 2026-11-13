'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {postURL,siteURL,mediaURL,describeStream,choices}=require('../browser-media.cjs');
function stream(id,audio,bitrate=500000,duration=57){const e=Buffer.from(JSON.stringify({xpv_asset_id:id,duration_s:duration,bitrate,vencode_tag:audio?'dash_audio':'dash_video'})).toString('base64url');return `https://scontent-test.cdninstagram.com/a.mp4?efg=${e}&bytestart=100&byteend=200&sig=keepme`}
test('post and media boundaries reject credentials, local addresses and deceptive hosts',()=>{
 assert.equal(postURL('https://www.instagram.com/p/Abcd/?tracking=1'),'https://www.instagram.com/p/Abcd/');
 for(const u of ['http://www.instagram.com/p/a/','https://instagram.com.evil.test/p/a/','https://www.instagram.com:9000/p/a/','https://user:pass@instagram.com/p/a/','https://www.instagram.com/'])assert.throws(()=>postURL(u));
 for(const u of ['file:///tmp/a','http://127.0.0.1/a','https://cdninstagram.com.evil.test/a','https://evilfbcdn.net/a','https://user:pass@a.fbcdn.net/a'])assert.throws(()=>mediaURL(u));
 assert.ok(siteURL('https://www.facebook.com/login/'));assert.ok(!siteURL('https://facebook.com.evil.test/login/'));
 const url=new URL(mediaURL(stream(1,false)));assert.equal(url.searchParams.get('sig'),'keepme');assert.equal(url.searchParams.get('bytestart'),null);assert.equal(url.searchParams.get('byteend'),null);
});
test('normal visible video matches duration, pairs same asset only, uses best observed stream',()=>{
 const visible=[{kind:'video',url:'blob:https://www.instagram.com/123',duration:57.66}];
 const r=choices(visible,[stream(1,false,1000),stream(1,false,2000),stream(1,true),stream(2,true),stream(3,false,900000,14)]);
 assert.equal(r.length,1);assert.equal(r[0].asset,'1');assert.equal(describeStream(r[0].video).bitrate,2000);assert.equal(describeStream(r[0].audio).id,'1');
});
test('ambiguous same-duration streams are refused; missing audio is explicit',()=>{
 const visible=[{kind:'video',url:'blob:abc',duration:57.5}];
 assert.deepEqual(choices(visible,[stream(1,false),stream(2,false),stream(2,true)]),[]);
 const r=choices(visible,[stream(1,false)]);assert.equal(r.length,1);assert.equal(r[0].muted,true);assert.match(r[0].label,/무음/);
 assert.deepEqual(choices([...visible,...visible],[stream(1,false)]),[]);
});
test('DRM, absent video, invalid metadata, unobserved streams are never fabricated',()=>{
 assert.deepEqual(choices([{kind:'video',url:'blob:abc',duration:57,encrypted:true}],[stream(1,false)]),[]);
 assert.deepEqual(choices([{kind:'video',url:'blob:abc',duration:57}],[]),[]);
 assert.deepEqual(choices([],[stream(1,false)]),[]);
 assert.equal(describeStream('https://a.fbcdn.net/a.mp4?efg=invalid'),null);
});
test('visible images stay explicit and duplicates collapse',()=>{
 const image={kind:'image',url:'https://a.cdninstagram.com/image.jpg',width:1080,height:1350};
 assert.equal(choices([image,image],[]).length,1);assert.equal(choices([{...image,url:'https://unrelated.example/a.jpg'}],[]).length,0);
});
test('large Instagram asset IDs retain exact digits and match normal playback',()=>{
 const encoded=Buffer.from('{"xpv_asset_id":17848020087643719,"duration_s":8,"bitrate":173650,"vencode_tag":"dash_video"}').toString('base64url');
 const url='https://a.cdninstagram.com/video.mp4?efg='+encoded;
 assert.equal(describeStream(url).id,'17848020087643719');
 const found=choices([{kind:'video',url:'blob:visible',duration:8.3}],[url]);
 assert.equal(found.length,1);assert.equal(found[0].asset,'17848020087643719');
});
