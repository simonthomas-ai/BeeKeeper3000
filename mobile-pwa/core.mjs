export const SOURCE_KEYS = Object.freeze(["id","observed_at","station_id","species","confidence","prey_detected","origin"]);
export const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
export const MAX_PHOTO_PIXELS = 16_000_000;

const PNG_SIGNATURE = new Uint8Array([137,80,78,71,13,10,26,10]);
const JPEG_SOF_MARKERS = new Set([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf]);

export function assertPhotoDimensions(width,height){
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1)throw new TypeError("Ungültige Bildabmessungen");
 if(width>Math.floor(MAX_PHOTO_PIXELS/height))throw new RangeError("Foto überschreitet die lokale Grenze von 16 Megapixeln");
 return {width,height};
}
function ascii(bytes,start,length){return String.fromCharCode(...bytes.subarray(start,start+length))}
function readU32BE(bytes,offset){return ((bytes[offset]*0x1000000)+(bytes[offset+1]<<16)+(bytes[offset+2]<<8)+bytes[offset+3])>>>0}
function readU32LE(bytes,offset){return (bytes[offset]|(bytes[offset+1]<<8)|(bytes[offset+2]<<16)|(bytes[offset+3]<<24))>>>0}
function readU24LE(bytes,offset){return bytes[offset]|(bytes[offset+1]<<8)|(bytes[offset+2]<<16)}
function pngDimensions(bytes){
 if(bytes.length<45||!PNG_SIGNATURE.every((value,index)=>bytes[index]===value)||readU32BE(bytes,8)!==13||ascii(bytes,12,4)!=="IHDR")throw new Error("PNG-Bild ist ungültig oder unvollständig");
 let offset=8,foundEnd=false;
 while(offset+12<=bytes.length){
  const size=readU32BE(bytes,offset),type=ascii(bytes,offset+4,4);
  if(size>bytes.length-offset-12)throw new Error("PNG-Bild enthält einen ungültigen Chunk");
  if(type==="acTL")throw new Error("Animierte PNG-Bilder werden nicht unterstützt");
  offset+=size+12;
  if(type==="IEND"){foundEnd=true;break}
 }
 if(!foundEnd)throw new Error("PNG-Bild enthält keinen vollständigen End-Chunk");
 return assertPhotoDimensions(readU32BE(bytes,16),readU32BE(bytes,20));
}
function jpegDimensions(bytes){
 if(bytes.length<4||bytes[0]!==0xff||bytes[1]!==0xd8)throw new Error("JPEG-Bild ist ungültig oder stimmt nicht mit dem Dateityp überein");
 let offset=2;
 while(offset<bytes.length){
  if(bytes[offset]!==0xff)throw new Error("JPEG-Bild enthält eine ungültige Markerfolge");
  while(offset<bytes.length&&bytes[offset]===0xff)offset++;
  if(offset>=bytes.length)break;
  const marker=bytes[offset++];
  if(marker===0xd9||marker===0xda)break;
  if(marker===0xd8||marker===0x01||(marker>=0xd0&&marker<=0xd7))continue;
  if(offset+2>bytes.length)throw new Error("JPEG-Bild enthält einen unvollständigen Marker");
  const segmentLength=(bytes[offset]<<8)|bytes[offset+1];
  if(segmentLength<2||segmentLength>bytes.length-offset)throw new Error("JPEG-Bild enthält einen ungültigen Segmentumfang");
  const payload=offset+2;
  if(marker===0xe2&&segmentLength>=6&&ascii(bytes,payload,4)==="MPF\u0000")throw new Error("Mehrbild-JPEGs werden nicht unterstützt");
  if(JPEG_SOF_MARKERS.has(marker)){
   if(segmentLength<7)throw new Error("JPEG-Bild enthält ungültige Abmessungen");
   const height=(bytes[offset+3]<<8)|bytes[offset+4];
   const width=(bytes[offset+5]<<8)|bytes[offset+6];
   return assertPhotoDimensions(width,height);
  }
  offset+=segmentLength;
 }
 throw new Error("JPEG-Abmessungen konnten nicht sicher gelesen werden");
}
function webpDimensions(bytes){
 if(bytes.length<26||ascii(bytes,0,4)!=="RIFF"||ascii(bytes,8,4)!=="WEBP"||readU32LE(bytes,4)+8!==bytes.length)throw new Error("WebP-Bild ist ungültig oder unvollständig");
 let offset=12,dimensions=null;
 while(offset+8<=bytes.length){
  const type=ascii(bytes,offset,4),size=readU32LE(bytes,offset+4),data=offset+8;
  if(size>bytes.length-data)throw new Error("WebP-Bild enthält einen ungültigen Chunk");
  if(type==="ANIM"||type==="ANMF")throw new Error("Animierte WebP-Bilder werden nicht unterstützt");
  if(type==="VP8X"){
   if(size<10)throw new Error("WebP-Erweiterungsheader ist ungültig");
   if(bytes[data]&0x02)throw new Error("Animierte WebP-Bilder werden nicht unterstützt");
   dimensions=assertPhotoDimensions(1+readU24LE(bytes,data+4),1+readU24LE(bytes,data+7));
   break;
  }
  if(type==="VP8 "&&size>=10&&bytes[data+3]===0x9d&&bytes[data+4]===0x01&&bytes[data+5]===0x2a){
   dimensions=assertPhotoDimensions(((bytes[data+7]<<8)|bytes[data+6])&0x3fff,((bytes[data+9]<<8)|bytes[data+8])&0x3fff);
   break;
  }
  if(type==="VP8L"&&size>=5&&bytes[data]===0x2f){
   const b1=bytes[data+1],b2=bytes[data+2],b3=bytes[data+3],b4=bytes[data+4];
   const width=1+(((b2&0x3f)<<8)|b1);
   const height=1+(((b4&0x0f)<<10)|(b3<<2)|((b2&0xc0)>>6));
   dimensions=assertPhotoDimensions(width,height);
   break;
  }
  offset=data+size+(size&1);
 }
 if(!dimensions)throw new Error("WebP-Abmessungen konnten nicht sicher gelesen werden");
 return dimensions;
}
export async function inspectPhotoFile(file){
 if(!file||typeof file.type!=="string"||!Number.isSafeInteger(file.size)||file.size<1||file.size>MAX_PHOTO_BYTES||typeof file.arrayBuffer!=="function")throw new TypeError("Bitte ein Bild bis 8 MB auswählen");
 const type=file.type.toLowerCase();
 if(!["image/jpeg","image/png","image/webp"].includes(type))throw new TypeError("Nur JPEG-, PNG- und WebP-Bilder werden unterstützt. HEIC bitte lokal als JPEG speichern");
 const buffer=await file.arrayBuffer();
 if(!(buffer instanceof ArrayBuffer))throw new TypeError("Bilddaten konnten nicht sicher gelesen werden");
 const bytes=new Uint8Array(buffer);
 if(bytes.length!==file.size)throw new Error("Bilddatei wurde während der Prüfung verändert");
 const dimensions=type==="image/png"?pngDimensions(bytes):type==="image/jpeg"?jpegDimensions(bytes):webpDimensions(bytes);
 return {type,...dimensions};
}
export async function preparePhotoBlob(file,{decodeImage,createCanvas}={}){
 await inspectPhotoFile(file);
 const decode=decodeImage||((source)=>{
  if(typeof createImageBitmap!=="function")throw new Error("Bildbereinigung wird in diesem Browser nicht unterstützt");
  return createImageBitmap(source);
 });
 const makeCanvas=createCanvas||(()=>document.createElement("canvas"));
 const bmp=await decode(file);
 try{
  assertPhotoDimensions(bmp.width,bmp.height);
  const scale=Math.min(1,1600/Math.max(bmp.width,bmp.height));
  const canvas=makeCanvas();
  canvas.width=Math.max(1,Math.round(bmp.width*scale));
  canvas.height=Math.max(1,Math.round(bmp.height*scale));
  const ctx=canvas.getContext("2d");
  if(!ctx||typeof canvas.toBlob!=="function")throw new Error("Bildbereinigung wird in diesem Browser nicht unterstützt");
  ctx.drawImage(bmp,0,0,canvas.width,canvas.height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/jpeg",.82));
  if(!blob||blob.size>MAX_PHOTO_BYTES)throw new Error("Foto konnte nicht sicher verkleinert werden");
  return blob;
 }finally{
  try{bmp?.close?.()}catch{}
 }
}
export function confidenceScore(level){const scores={low:0.25,medium:0.55,high:0.85};if(!Object.hasOwn(scores,level))throw new TypeError("Unbekannte Einschätzungsstufe");return scores[level]}
export function validateSourceEvent(event){
 if(!event||typeof event!=="object"||Array.isArray(event))throw new TypeError("Ereignis muss ein Objekt sein");
 const keys=Object.keys(event).sort(),expected=[...SOURCE_KEYS].sort();
 if(keys.length!==expected.length||keys.some((key,i)=>key!==expected[i]))throw new TypeError("Nicht erlaubte oder fehlende Felder");
 if(typeof event.id!=="string"||!/^[\x21-\x7e]{1,128}$/.test(event.id))throw new TypeError("Ungültige Ereignis-ID");
 if(typeof event.station_id!=="string"||!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/.test(event.station_id))throw new TypeError("Ungültige Stationskennung");
 if(typeof event.observed_at!=="string"||!/(?:Z|[+-]\d{2}:\d{2})$/i.test(event.observed_at)||!Number.isFinite(Date.parse(event.observed_at)))throw new TypeError("Zeitstempel benötigt ISO-8601 mit Zeitzone");
 if(typeof event.species!=="string"||!event.species.trim()||event.species.length>160||/[\u0000-\u001f\u007f]/.test(event.species))throw new TypeError("Ungültige Artangabe");
 if(typeof event.confidence!=="number"||!Number.isFinite(event.confidence)||event.confidence<0||event.confidence>1)throw new TypeError("Einschätzung muss zwischen 0 und 1 liegen");
 if(typeof event.prey_detected!=="boolean")throw new TypeError("prey_detected muss boolesch sein");
 if(event.origin!=="manual_observation")throw new TypeError("Mobile-PWA-Ereignisse müssen als manuelle Beobachtung gekennzeichnet sein");
 return event;
}
export function toSourceEvent(report){if(!report||typeof report!=="object")throw new TypeError("Lokaler Bericht fehlt");return validateSourceEvent({id:report.event_id,observed_at:report.observed_at,station_id:report.station_id,species:report.species,confidence:report.confidence,prey_detected:report.prey_detected,origin:"manual_observation"})}
export function makeStationId(uuid){if(typeof uuid!=="string"||!/^[0-9a-f-]{16,36}$/i.test(uuid))throw new TypeError("Ungültige UUID");return "mobile-"+uuid.toLowerCase()}

export function waitForOrientationSample(target, {
 timeoutMs=5000,
 now=()=>new Date().toISOString(),
 setTimer=setTimeout,
 clearTimer=clearTimeout
}={}){
 if(!target||typeof target.addEventListener!=="function"||typeof target.removeEventListener!=="function")throw new TypeError("Sensorziel muss Event-Listener unterstützen");
 if(!Number.isFinite(timeoutMs)||timeoutMs<100||timeoutMs>60000)throw new RangeError("Sensor-Timeout muss zwischen 100 und 60000 ms liegen");
 if(typeof now!=="function"||typeof setTimer!=="function"||typeof clearTimer!=="function")throw new TypeError("Zeit- und Timerfunktionen sind erforderlich");
 return new Promise((resolve,reject)=>{
  let timer;
  let settled=false;
  const cleanup=()=>{
   target.removeEventListener("deviceorientation",handler);
   if(timer!==undefined)clearTimer(timer);
  };
  const fail=error=>{
   if(settled)return;
   settled=true;
   cleanup();
   reject(error);
  };
  const handler=event=>{
   // Some devices emit an initial event with null alpha while the sensor
   // initializes. Ignore it; keep listening until a usable sample arrives.
   if(!event||!Number.isFinite(event.alpha)||event.alpha<0||event.alpha>360)return;
   settled=true;
   const sample={
    alpha_deg:event.alpha,
    beta_deg:Number.isFinite(event.beta)?event.beta:null,
    gamma_deg:Number.isFinite(event.gamma)?event.gamma:null,
    absolute:event.absolute===true,
    captured_at:now(),
    status:"raw_uncalibrated_not_for_triangulation"
   };
   cleanup();
   resolve(sample);
  };
  target.addEventListener("deviceorientation",handler);
  timer=setTimer(()=>fail(new Error("Keine Sensordaten empfangen.")),timeoutMs);
 });
}
