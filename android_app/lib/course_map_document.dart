import 'dart:convert';

import 'course_map_data.dart';

// Encode every value crossing the HTML/script boundary. Place names never become
// HTML; the SDK overlays use textContent and setAttribute exclusively.
String _scriptJson(Object? value) => jsonEncode(value)
    .replaceAll('<', r'\u003c')
    .replaceAll('>', r'\u003e')
    .replaceAll('&', r'\u0026')
    .replaceAll('\u2028', r'\u2028')
    .replaceAll('\u2029', r'\u2029');

Map<String, dynamic> courseMapPayload({
  required List<CourseMapStop> stops,
  required int? selectedIndex,
  required int revision,
  CourseRouteData? route,
  int? selectedLeg,
}) => {
  'stops': stops.map((stop) => stop.toJson()).toList(),
  'selectedIndex': selectedIndex,
  'revision': revision,
  'route': route?.toJson(),
  'selectedLeg': selectedLeg != null && courseMapHasLeg(stops, selectedLeg)
      ? selectedLeg
      : null,
};

String courseMapUpdateScript(Map<String, dynamic> payload) =>
    'window.courseMap && window.courseMap.render(${_scriptJson(payload)});';

String courseMapDocument({
  required String javascriptKey,
  required Map<String, dynamic> payload,
}) => _document
    .replaceFirst('__JAVASCRIPT_KEY__', _scriptJson(javascriptKey))
    .replaceFirst('__INITIAL_STATE__', _scriptJson(payload));

const _document = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="referrer" content="strict-origin-when-cross-origin">
<style>
html,body,#map{margin:0;width:100%;height:100%;overflow:hidden;background:#fff8f3}
body{font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif}
.stop{width:44px;height:44px;padding:0;border:0;background:transparent;color:#914b33;display:flex;align-items:flex-end;justify-content:center;touch-action:manipulation}
.pin{width:24px;height:30px;position:relative;display:block;background:#914b33;clip-path:path('M12 30 C10 27 1 20 1 12 A11 11 0 0 1 23 12 C23 20 14 27 12 30 Z')}
.pin-inner{position:absolute;inset:0;clip-path:inherit;background:#fffdfb;transform:scale(.87);transform-origin:50% 42%}
.pin-number{position:absolute;top:0;left:0;width:24px;height:24px;display:flex;align-items:center;justify-content:center;color:#914b33;font-family:inherit;font-size:12px;font-weight:500;line-height:1}
.stop[aria-pressed=true] .pin-inner{background:#914b33}
.stop[aria-pressed=true] .pin-number{color:#fffdfb}
.stop-compact{align-items:center}
.pin.compact{width:20px;height:20px;box-sizing:border-box;border:1.5px solid #914b33;border-radius:50%;clip-path:none;background:#fffdfb}
.pin.compact .pin-inner{display:none}
.pin.compact .pin-number{width:17px;height:17px;font-size:11px}
.stop[aria-pressed=true] .pin.compact{background:#914b33}
.pin.leg-pin{width:22px;height:27px;clip-path:path('M11 27 C9 24 1 18 1 11 A10 10 0 0 1 21 11 C21 18 13 24 11 27 Z')}
.pin.leg-pin .pin-number{width:22px;height:22px}
.stop.destination .pin-inner{background:#914b33}
.stop.destination .pin-number{color:#fffdfb}
.connections{display:block;overflow:visible;pointer-events:none}
#fit{position:absolute;right:10px;top:10px;z-index:10;min-height:44px;padding:6px 10px;border:1px solid #eadfd6;border-radius:10px;background:#fffdfb;color:#914b33;font-size:12px}
</style></head><body><div id="map" role="group" aria-label="코스 장소 지도"></div>
<button id="fit" type="button" aria-label="모든 장소 보기">전체 보기</button>
<script>
(()=>{
'use strict';
let state=__INITIAL_STATE__, map=null, overlays=[], buttons=new Map(), signature='', tiled=false, failed=false, closed=false, layoutFrame=0, connectionFrame=0, connectionSignature='', connections=null, connectionOverlay=null, motionObserver=null, resizeObserver=null, overlayGeneration=0, firstViewportRequested=false, firstViewportReconciled=false, viewportFrame=0;
const key=__JAVASCRIPT_KEY__;
function emit(type,extra={}){if(!closed&&window.CourseMapBridge)window.CourseMapBridge.postMessage(JSON.stringify({type,revision:state.revision,...extra}));}
function fail(){if(failed)return;failed=true;emit('error');}
function fit(){
 const host=document.getElementById('map');
 if(!map||!state.stops.length||host.clientWidth<=0||host.clientHeight<=0)return;
 const stops=visibleStops();if(!stops.length)return;
 const points=[...stops.map(s=>[s.lng,s.lat]),...routePaths().flatMap(path=>path.points)];
 const positions=new Set(points.map(point=>point.join(',')));
 if(positions.size===1){map.setLevel(4);map.setCenter(new kakao.maps.LatLng(stops[0].lat,stops[0].lng));return;}
 const bounds=new kakao.maps.LatLngBounds();points.forEach(point=>bounds.extend(new kakao.maps.LatLng(point[1],point[0])));
 map.setBounds(bounds,64,40,40,40);
}
function validLeg(index){return Number.isInteger(index)&&state.stops.some(stop=>stop.index===index)&&state.stops.some(stop=>stop.index===index+1);}
function visibleStops(){return validLeg(state.selectedLeg)?state.stops.filter(stop=>stop.index===state.selectedLeg||stop.index===state.selectedLeg+1):state.stops;}
function highlight(pan=true){
 overlays.forEach(overlay=>overlay.setZIndex(2));
 buttons.forEach((item,index)=>{const selected=index===state.selectedIndex;item.button.setAttribute('aria-pressed',String(selected));if(selected)item.overlay.setZIndex(5);});
 const selected=buttons.get(state.selectedIndex);
 if(pan&&selected&&!map.getBounds().contain(selected.position))map.panTo(selected.position);
}
function selectStop(index,generation){
 if(closed||generation!==overlayGeneration||!buttons.has(index))return;
 state.selectedIndex=index;highlight();emit('select',{index});
}
function routePaths(){
 return (state.route?.segments||[]).filter(segment=>segment.status==='ready'&&segment.toIndex===segment.fromIndex+1&&(!validLeg(state.selectedLeg)||segment.fromIndex===state.selectedLeg)).flatMap(segment=>segment.paths.map(path=>({...path,fromIndex:segment.fromIndex,toIndex:segment.toIndex})));
}
function connectVisits(){
 if(!connections||closed||!map)return;
 // The SVG belongs to the SDK overlay pane. Its camera matrix supplies the
 // same pan/zoom animation as the pins; geometry stays in that local frame.
 const camera=connections.getScreenCTM();if(!camera)return;
 const projection=map.getProjection(),anchor=projection.pointFromCoords(connectionOverlay.getPosition());
 const inverse=camera.inverse(),width=Number(connections.getAttribute('width')),height=Number(connections.getAttribute('height'));
 const center=map.getCenter(),next=[state.revision,state.selectedLeg,map.getLevel(),center.getLat(),center.getLng(),anchor.x,anchor.y,width,height].join(',');
 if(next===connectionSignature)return;connectionSignature=next;
 connections.replaceChildren();
 const point=coordinates=>{
  const projected=projection.pointFromCoords(new kakao.maps.LatLng(coordinates[1],coordinates[0]));
  const local=connections.createSVGPoint();local.x=projected.x-anchor.x+width/2;local.y=projected.y-anchor.y+height/2;
  return local.matrixTransform(camera).matrixTransform(inverse);
 };
 const paths=routePaths();
 paths.forEach(path=>{
  if(path.points.length<2)return;
  const d=path.points.map((coordinates,index)=>{const p=point(coordinates);return (index?'L':'M')+p.x+','+p.y;}).join(' ');
  [['visit-route-outline','#fffdfb','7'],['visit-route','#914b33','5.6'],['visit-route-center','#fffdfb','1.2']].forEach(([className,color,width])=>{
   const route=document.createElementNS(connections.namespaceURI,'path');route.classList.add(className);route.setAttribute('data-from',String(path.fromIndex));route.setAttribute('data-to',String(path.toIndex));route.setAttribute('data-mode',path.mode);route.setAttribute('d',d);route.setAttribute('fill','none');route.setAttribute('stroke',color);route.setAttribute('stroke-width',width);route.setAttribute('stroke-linecap','round');route.setAttribute('stroke-linejoin','round');route.setAttribute('vector-effect','non-scaling-stroke');
   if(className==='visit-route-center')route.setAttribute('stroke-dasharray','7 6');
   connections.appendChild(route);
  });
 });
}
function trackConnections(){
 if(closed)return;
 connectVisits();connectionFrame=requestAnimationFrame(trackConnections);
}
function layoutOverlays(){
 if(!map||closed)return;
 const host=document.getElementById('map');if(host.clientWidth<=0||host.clientHeight<=0)return;
 const width=String(host.clientWidth),height=String(host.clientHeight);
 const resized=connections.getAttribute('width')!==width||connections.getAttribute('height')!==height;
 connections.setAttribute('width',width);connections.setAttribute('height',height);
 if(resized)connectionOverlay.setContent(connections);
 connectionOverlay.setPosition(map.getCenter());
 overlayGeneration++;const generation=overlayGeneration;
 overlays.forEach(o=>o.setMap(null));overlays=[];buttons.clear();
 const compact=!validLeg(state.selectedLeg)&&Number(width)<310;
 visibleStops().forEach(stop=>{
  const position=new kakao.maps.LatLng(stop.lat,stop.lng),button=document.createElement('button');button.type='button';button.className='stop'+(compact?' stop-compact':'')+(validLeg(state.selectedLeg)&&stop.index===state.selectedLeg+1?' destination':'');button.setAttribute('data-index',String(stop.index));button.setAttribute('aria-label',stop.sequence+'번 '+stop.name);
  const pin=document.createElement('span');pin.className='pin'+(compact?' compact':validLeg(state.selectedLeg)?' leg-pin':'');pin.setAttribute('aria-hidden','true');const inner=document.createElement('span');inner.className='pin-inner';const label=document.createElement('span');label.className='pin-number';label.textContent=String(stop.sequence);pin.append(inner,label);button.appendChild(pin);
  const overlay=new kakao.maps.CustomOverlay({position,content:button,xAnchor:.5,yAnchor:compact ? .5 : 1,zIndex:2,clickable:true});
  button.addEventListener('click',event=>{event.stopPropagation();if(closed||generation!==overlayGeneration||buttons.get(stop.index)?.button!==button)return;selectStop(stop.index,generation);});
  buttons.set(stop.index,{button,overlay,position});overlay.setMap(map);overlays.push(overlay);
 });
 document.getElementById('map').setAttribute('aria-label',validLeg(state.selectedLeg)?(state.selectedLeg+1)+'번에서 '+(state.selectedLeg+2)+'번까지 실제 경로 지도':'전체 코스 실제 경로 지도');
 connectVisits();
 highlight(false);
}
function scheduleLayout(){cancelAnimationFrame(layoutFrame);layoutFrame=requestAnimationFrame(layoutOverlays);}
function draw(){
 if(!map)return;
 const next=JSON.stringify([state.stops,state.route,state.selectedLeg]);
 if(next!==signature){
  signature=next;
  fit();
  layoutOverlays();
 }
 highlight();
 if(tiled)emit('ready');
}
function reconcileViewport(){
 if(closed||firstViewportReconciled)return;
 firstViewportRequested=true;if(!map||viewportFrame)return;
 // The native loading layer has just been removed. Allow the platform view's
 // first visible frame to settle before measuring the SDK viewport once.
 viewportFrame=requestAnimationFrame(()=>{viewportFrame=requestAnimationFrame(()=>{
  viewportFrame=0;if(closed||!map||firstViewportReconciled)return;
  const host=document.getElementById('map');if(host.clientWidth<=0||host.clientHeight<=0)return;
  firstViewportReconciled=true;map.relayout();fit();layoutOverlays();
 });});
}
window.courseMap={reconcileViewport,render(next){
 if(closed||next.revision<state.revision)return;
 state=next;if(!validLeg(state.selectedLeg))state.selectedLeg=null;
 draw();
},close(){
 closed=true;overlayGeneration++;cancelAnimationFrame(layoutFrame);cancelAnimationFrame(connectionFrame);cancelAnimationFrame(viewportFrame);if(motionObserver)motionObserver.disconnect();if(resizeObserver)resizeObserver.disconnect();
 if(connections)connections.replaceChildren();if(connectionOverlay)connectionOverlay.setMap(null);
 overlays.forEach(overlay=>overlay.setMap(null));overlays=[];buttons.clear();
}};
emit('document');
document.getElementById('fit').addEventListener('click',()=>{if(closed)return;state.selectedLeg=null;signature='';draw();emit('overview');});
const script=document.createElement('script');
script.src='https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey='+encodeURIComponent(key);
script.onerror=fail;
script.onload=()=>{
 if(closed)return;
 if(!window.kakao?.maps?.load){fail();return;}
 kakao.maps.load(()=>{
  if(closed)return;
  try{
   const first=state.stops[0];if(!first){fail();return;}
   map=new kakao.maps.Map(document.getElementById('map'),{center:new kakao.maps.LatLng(first.lat,first.lng),level:6});
   connections=document.createElementNS('http://www.w3.org/2000/svg','svg');connections.classList.add('connections');connections.setAttribute('aria-hidden','true');
   connectionOverlay=new kakao.maps.CustomOverlay({position:map.getCenter(),content:connections,xAnchor:.5,yAnchor:.5,zIndex:1});connectionOverlay.setMap(map);
   trackConnections();
   motionObserver=new MutationObserver(connectVisits);motionObserver.observe(document.getElementById('map'),{subtree:true,attributes:true,attributeFilter:['style']});
   kakao.maps.event.addListener(map,'tilesloaded',()=>{tiled=true;emit('ready');});
   kakao.maps.event.addListener(map,'zoom_changed',scheduleLayout);
   kakao.maps.event.addListener(map,'idle',scheduleLayout);
   draw();
   if(window.ResizeObserver){resizeObserver=new ResizeObserver(()=>{if(closed)return;const host=document.getElementById('map');if(host.clientWidth<=0||host.clientHeight<=0)return;map.relayout();fit();scheduleLayout();if(firstViewportRequested&&!firstViewportReconciled)reconcileViewport();});resizeObserver.observe(document.getElementById('map'));}
  }catch(_){fail();}
 });
};
document.head.appendChild(script);
})();
</script></body></html>''';
