import fs from 'node:fs';
import { toMusicXML, type Note } from '../../lib/music/score';
const cases: Record<string,Note[]> = JSON.parse(fs.readFileSync('.work/madmom-quantization/cases.json','utf8'));
const rows=[];
for (const [name,notes] of Object.entries(cases)) {
  for (let phase=0;phase<3;phase++) {
    // Beat-unit timeline: BPM=60 is a serialization device, not a tempo estimate.
    const xml=toMusicXML(notes.map(n=>({...n,start:n.start+phase})),{title:`${name} diagnostic`,bpm:60,beats:3,key:0});
    fs.writeFileSync(`.work/madmom-quantization/${name}-phase${phase}.musicxml`,xml);
    const rests=[...xml.matchAll(/<note><rest\/><duration>(\d+)<\/duration>/g)].map(m=>Number(m[1]));
    rows.push({case:name,phase,rests:rests.length,sixteenthRests:rests.filter(n=>n===1).length,shortNotes:notes.filter(n=>n.duration<=.25).length,measures:(xml.match(/<measure /g)||[]).length});
  }
}
fs.writeFileSync('.work/madmom-quantization/notation-metrics.json',JSON.stringify(rows,null,2));console.log(rows);
