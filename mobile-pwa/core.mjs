export const SOURCE_KEYS = Object.freeze(["id","observed_at","station_id","species","confidence","prey_detected"]);
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
 return event;
}
export function toSourceEvent(report){if(!report||typeof report!=="object")throw new TypeError("Lokaler Bericht fehlt");return validateSourceEvent({id:report.event_id,observed_at:report.observed_at,station_id:report.station_id,species:report.species,confidence:report.confidence,prey_detected:report.prey_detected})}
export function makeStationId(uuid){if(typeof uuid!=="string"||!/^[0-9a-f-]{16,36}$/i.test(uuid))throw new TypeError("Ungültige UUID");return "mobile-"+uuid.toLowerCase()}
