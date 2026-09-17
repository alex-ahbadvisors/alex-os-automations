#!/usr/bin/env python3
"""Execute the shipped n8n JavaScript against synthetic data; optionally real PG.

python3 scripts/tests/test-crm-capture-identity.py
python3 scripts/tests/test-crm-capture-identity.py --postgres --insert-guard /path/to/reviewed/guard.sql

The PostgreSQL image is already installed and pinned: no pull/network/ports/host
mounts. The optional previously reviewed guard is hash-bound, not deployed or
changed by this package. No credentials, real contacts, or live writes are used.
"""
import argparse
import ast
import re
import hashlib
import json
import pathlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'scripts/tests/fixtures/crm-capture-identity.json'
CAPTURE = ROOT / 'n8n-workflows/capture-email-contacts.json'
REVERSE = ROOT / 'n8n-workflows/clickup-contact-review-supabase-reverse.json'
BASE = '2862c9c15bd4e9acc2a4df8ce173c162476820d6'
IMAGE = 'sha256:78df81b1442dcc764c1104154da7162635e40cfffe67579c42a1c1b96dfc209c'
GUARD_SHA256 = 'c2b5ed60d7acb1eaec07a604dbeb3d6dd61b2c7bc7474c724577fdc4f5cb9330'

NODE_TESTS = r"""
const fs = require('fs'), assert = require('assert/strict');
const {workflow:w, fixture:f, envelopes:dbEnvelopes} = JSON.parse(fs.readFileSync(0,'utf8'));
const nodes = Object.fromEntries(w.nodes.map(n => [n.name,n]));
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
let checks = 0;
function check(fn) { fn(); checks++; }
const copy = x => JSON.parse(JSON.stringify(x));
const items = values => values.map(json => ({json}));
function refs(data) {
  return name => ({all:()=>{if (!(name in data)) throw Error('not executed');return data[name];},
    first:()=>{if (!(name in data) || !data[name].length) throw Error('no data');return data[name][0];}});
}
async function run(name,input,data) {
  return new AsyncFunction('$','$input',nodes[name].parameters.jsCode)(refs(data),
    {all:()=>input,first:()=>input[0]});
}
function expression(source,data,json={}) {
  assert(source.startsWith('={{') && source.endsWith('}}'));
  return new Function('$','$json','return ('+source.slice(3,-2)+')')(refs(data),json);
}
// Independent fixture lookup model; real PostgreSQL results are also fed into
// these exact JS nodes when --postgres is selected.
function lookup(emails,contacts=f.contacts) {
  const byId = new Map(contacts.map(c=>[c.id,c]));
  return {statusCode:200,body:{schema_version:1,identities:[...new Set(emails)].sort().map(email=>({email,
    owners:contacts.filter(c=>(c.emails||[]).some(e=>e.trim().toLowerCase()===email)).map(owner=>{
      let c=owner,path=[],resolution='ok';
      while (true) {
        if (!c) {resolution='missing_target';break;}
        if (path.includes(c.id)) {path.push(c.id);resolution='cycle';break;}
        path.push(c.id);
        if (!c.merged_into) {if(c.review_status==='merged')resolution='merged_without_target';break;}
        if(path.length===100) {resolution='depth_limit';break;}
        const target=c.merged_into;c=byId.get(target);
        if(!c)path.push(target);
      }
      return {owner_id:owner.id,canonical_id:resolution==='ok'?c.id:null,resolution,path,
        review_status:c?.review_status??null,relationship_tier:c?.relationship_tier??null,updated_at:c?.updated_at??null};
    })}))}};
}
async function resolve(participants,response) {
  return run('Resolve',items([response]),{'Participants':items(participants)});
}
const part=email=>({contact_email:email.trim().toLowerCase(),contact_name:'Synthetic',
  identity_error:/^[^\s@]+@[^\s@]+$/.test(email.trim())?null:'invalid_email',
  lookup_eligible:/^[^\s@]+@[^\s@]+$/.test(email.trim())});
(async()=>{
  for(const c of f.cases) {
    const p=part(c.email);
    const result=(await resolve([p],lookup([p.contact_email])))[0].json;
    check(()=>assert.equal(result.action,c.action,c.name));
    check(()=>assert.equal(result.contact_id??null,c.contact_id,c.name));
    check(()=>assert.equal(result.reason??null,c.reason,c.name));
    if(dbEnvelopes) {
      const actual=(await resolve([p],{statusCode:200,body:dbEnvelopes[c.name]}))[0].json;
      check(()=>assert.deepEqual(actual,result,'PostgreSQL parity: '+c.name));
    }
  }
  const data={'Markdown':items([{messages:f.message}])};
  const participants=await run('Participants',[],data);
  check(()=>assert.deepEqual(participants.map(i=>i.json.contact_email),['keep@example.test','new@example.test']));
  check(()=>assert.equal(participants[0].pairedItem,0));
  for(const bad of [{error:{message:'timeout'}},{statusCode:500,body:{}},
    {statusCode:200,body:[]},{statusCode:200,body:{schema_version:1,identities:[]}},
    {statusCode:200,body:{schema_version:1,identities:[{email:'keep@example.test',owners:[]},{email:'keep@example.test',owners:[]}]}},
    {statusCode:200,body:{schema_version:2,identities:[]}},
    {statusCode:200,body:'not json'},
    {statusCode:403,body:{code:'42501',message:'crm_identity_lookup_visibility_unverified'}}]) {
    const result=await resolve([part('keep@example.test')],bad);
    check(()=>assert.equal(result[0].json.action,'hold'));
    check(()=>assert.equal(result[0].json.reason,'lookup_failed'));
  }
  for(const field of ['canonical_id','path','owner_id']) {
    const bad=lookup(['keep@example.test']);delete bad.body.identities[0].owners[0][field];
    check(()=>assert.equal((bad.body.identities[0].owners.length),1));
    const result=await resolve([part('keep@example.test')],bad);
    check(()=>assert.equal(result[0].json.action,'hold'));
  }
  // Long chains are bounded; email case/space owner collisions cannot win by order.
  const long = Array.from({length:101},(_,i)=>({id:'chain-'+i,emails:i?[]:['chain@example.test'],
    merged_into:i<100?'chain-'+(i+1):null,review_status:i<100?'merged':'kept'}));
  check(()=>assert.equal(lookup(['chain@example.test'],long).body.identities[0].owners[0].resolution,'depth_limit'));
  const longResult=await resolve([part('chain@example.test')],lookup(['chain@example.test'],long));
  check(()=>assert.equal(longResult[0].json.action,'hold'));
  const shuffled=await resolve([part('ambiguous@example.test')],lookup(['ambiguous@example.test'],[...f.contacts].reverse()));
  check(()=>assert.equal(shuffled[0].json.reason,'ambiguous_identity'));

  // Execute the actual expressions and JS along the capture graph. HTTP writes
  // are a synthetic store with a named guard conflict, never external requests.
  async function capture({emails=['keep@example.test','new@example.test'],response=null,
    race=false,unknownCommitted=false,lookupFailure=false,linkFailure=false,linkReceipt=null,attachments=true,contacts=copy(f.contacts)}={}) {
    const before=JSON.stringify(contacts), events=[],writes=[];
    const message={...copy(f.message),from_field:{address:'alex@ahbadvisors.com'},
      to_fields:emails.map(address=>({address})),cc_fields:[],attachments:attachments?f.message.attachments:[]};
    const d={'Markdown':items([{messages:message}]),'Create Interaction':items([{id:'synthetic-note'}])};
    d.Participants=await run('Participants',d['Create Interaction'],d);
    if(d.Participants.length) {
      const query=JSON.parse(expression(nodes['Match Contact'].parameters.jsonBody,d));
      d['Match Contact']=items([lookup(query.p_emails,contacts)]);
      d.Resolve=await run('Resolve',d['Match Contact'],d);
      const createParts=d.Resolve.filter(i=>expression(nodes.If.parameters.conditions.conditions[0].leftValue,d,i.json)==='create');
      check(()=>assert(query.p_emails.length<=f.input_isolation.batch_limit));
      check(()=>assert(query.p_emails.every(e=>e.length<=320 && !/\s/.test(e))));
      d['Create Contacts']=[];
      for(const input of createParts) {
        const payload=JSON.parse(expression(nodes['Create Contacts'].parameters.jsonBody,d,input.json));
        writes.push(payload);events.push('insert_attempt');
        const row={...payload,id:'new-'+writes.length,merged_into:null,relationship_tier:null,updated_at:'2026-09-01T00:00:00Z'};
        if(race||unknownCommitted||!response)contacts.push(row);
        d['Create Contacts'].push({json:response?copy(response):{statusCode:201,body:[row]}});
      }
      d['Merge Participants']=await run('Merge Participants',d['Create Interaction'],d);
      check(()=>assert.equal(d['Merge Participants'].length,1));
      d['Recheck Contact Identities']=items([lookupFailure?{error:{message:'synthetic read timeout'}}:lookup(query.p_emails,contacts)]);
      d['Build Junction Rows']=await run('Build Junction Rows',d['Recheck Contact Identities'],d);
      d['Valid Junction Rows']=await run('Valid Junction Rows',d['Build Junction Rows'],d);
      d['Create Junction Rows']=d['Valid Junction Rows'].map(i=>({json:linkFailure?{error:'synthetic link failure'}:linkReceipt?copy(linkReceipt):i.json}));
      for(const i of d['Create Junction Rows']) if(!i.json.error)events.push('junction_written');
    }
    if(!d.Participants.length) {
      d['Merge Participants']=await run('Merge Participants',d['Create Interaction'],d);
      check(()=>assert.equal(d['Merge Participants'].length,0));
    }
    // v1 executes this complete existing attachment branch before the bottom
    // diagnostic branch, including the legitimate zero-output case.
    d['Build Attachments']=await run('Build Attachments',d['Create Interaction'],d);
    if(d['Build Attachments'].length)events.push('attachment_saved');
    let error=null;
    try {d['Report Capture Identity Exceptions']=await run('Report Capture Identity Exceptions',d['Create Interaction'],d);}
    catch(e){error=e.message;events.push('identity_exception');}
    check(()=>assert.deepEqual(contacts.slice(0,JSON.parse(before).length),JSON.parse(before),'existing review decisions unchanged'));
    return {d,error,events,writes,contacts};
  }
  const normal=await capture();
  check(()=>assert.equal(normal.error,null));
  check(()=>assert.equal(normal.writes.length,1));
  check(()=>assert.equal(normal.d['Valid Junction Rows'].length,2));
  check(()=>assert(normal.d['Valid Junction Rows'].every(i=>i.json.match_method==='email')));
  for(const response of f.conflict_responses) {
    const result=await capture({response,race:true});
    check(()=>assert.equal(result.error,null,'named conflict '+response.statusCode));
    check(()=>assert.equal(result.writes.length,1));
    check(()=>assert.equal(result.d['Valid Junction Rows'].length,2));
    check(()=>assert.equal(result.contacts.filter(c=>c.emails.includes('new@example.test')).length,1));
  }
  for(const response of f.unknown_responses) for(const unknownCommitted of [false,true]) {
    const result=await capture({response,unknownCommitted});
    check(()=>assert.match(result.error,/crm_capture_identity_exception/));
    check(()=>assert.equal(result.writes.length,1));
    check(()=>assert.equal(result.d['Valid Junction Rows'].length,unknownCommitted?2:1));
    check(()=>assert(result.events.indexOf('attachment_saved')<result.events.indexOf('identity_exception')));
    check(()=>assert(!result.error.includes('@') && !result.error.includes('timeout')));
    if(unknownCommitted) {
      const retry=await capture({contacts:result.contacts});
      check(()=>assert.equal(retry.writes.length,0,'fresh discovery after lost response must not insert again'));
      check(()=>assert.equal(retry.d['Valid Junction Rows'].length,2));
    }
  }
  for(const statusCode of [400,409,500]) {
    const result=await capture({response:{statusCode,body:{message:'unrelated error'}}});
    check(()=>assert.match(result.error,/crm_capture_identity_exception/));
    check(()=>assert.equal(result.writes.length,1));
    check(()=>assert.equal(result.d['Valid Junction Rows'].length,1));
  }
  for(const emails of [[],['keep@example.test'],['new@example.test'],['ambiguous@example.test'],['keep@example.test','alias@example.test']]) {
    for(const attachments of [false,true]) {
      const result=await capture({emails,attachments});
      check(()=>assert.equal(Boolean(result.error),emails.includes('ambiguous@example.test')));
      check(()=>assert.equal(result.writes.length,emails.includes('new@example.test')?1:0));
      if(emails.includes('alias@example.test'))check(()=>assert.equal(result.d['Valid Junction Rows'].length,1));
    }
  }
  // Execute actual Participants and both RPC expressions with mixed invalid,
  // oversize and valid addresses: a malformed item cannot poison other links.
  for(const bad of [f.input_isolation.oversized_email,f.input_isolation.invalid_email,f.input_isolation.nul_email,f.input_isolation.unpaired_surrogate_email]) {
    const result=await capture({emails:['keep@example.test',bad,'new@example.test']});
    check(()=>assert.equal(result.writes.length,1));
    check(()=>assert.equal(result.d['Valid Junction Rows'].length,2));
    check(()=>assert.equal(result.d['Build Junction Rows'][0].json.exceptions.length,1));
    check(()=>assert.equal(result.d['Build Junction Rows'][0].json.exceptions[0].participant_index,1));
    check(()=>assert.match(result.error,/email_too_long|invalid_email/));
    const recheck=JSON.parse(expression(nodes['Recheck Contact Identities'].parameters.jsonBody,result.d));
    check(()=>assert.deepEqual(recheck.p_emails,['keep@example.test','new@example.test']));
  }
  const allBad=await capture({emails:[f.input_isolation.oversized_email,f.input_isolation.invalid_email]});
  check(()=>assert.equal(allBad.writes.length,0));
  check(()=>assert.equal(allBad.d['Valid Junction Rows'].length,0));
  check(()=>assert.equal(allBad.d['Build Junction Rows'][0].json.exceptions.length,2));
  check(()=>assert.match(allBad.error,/email_too_long/));
  const bulk=Array.from({length:f.input_isolation.overflow_participants},(_,i)=>({
    id:'synthetic-bulk-'+i,emails:['person'+i+'@'+f.input_isolation.bulk_domain],
    review_status:'kept',relationship_tier:1,merged_into:null}));
  const overflow=await capture({emails:bulk.map(c=>c.emails[0]),contacts:[...copy(f.contacts),...bulk]});
  check(()=>assert.equal(overflow.writes.length,0));
  check(()=>assert.equal(overflow.d['Valid Junction Rows'].length,1000));
  check(()=>assert.deepEqual(overflow.d['Build Junction Rows'][0].json.exceptions.map(e=>e.participant_index),[1000,1001]));
  check(()=>assert.match(overflow.error,/participant_lookup_limit/));
  const exactlyFull=await capture({emails:bulk.slice(0,1000).map(c=>c.emails[0]),contacts:[...copy(f.contacts),...bulk]});
  check(()=>assert.equal(exactlyFull.error,null));
  check(()=>assert.equal(exactlyFull.d['Valid Junction Rows'].length,1000));
  const invalidPlusFull=await capture({emails:[f.input_isolation.invalid_email,...bulk.slice(0,1000).map(c=>c.emails[0])],contacts:[...copy(f.contacts),...bulk]});
  check(()=>assert.equal(invalidPlusFull.d['Valid Junction Rows'].length,1000));
  check(()=>assert.equal(invalidPlusFull.d['Build Junction Rows'][0].json.exceptions.length,1));
  check(()=>assert.equal(invalidPlusFull.d['Build Junction Rows'][0].json.exceptions[0].reason,'invalid_email'));
  // The receipt contract is deliberately strict. These shapes are NOT proof
  // of missing DB rows; they must fail closed pending supervised readback.
  for(const linkReceipt of f.junction_receipt_shapes) {
    const result=await capture({linkReceipt});
    check(()=>assert.match(result.error,/junction_write_unverified/));
    check(()=>assert(result.events.indexOf('attachment_saved')<result.events.indexOf('identity_exception')));
  }
  const unresolvedConflict=await capture({response:f.conflict_responses[2]});
  check(()=>assert.match(unresolvedConflict.error,/identity_unresolved_after_insert/));
  const failedRead=await capture({lookupFailure:true});
  check(()=>assert.match(failedRead.error,/lookup_failed/));
  check(()=>assert(failedRead.events.indexOf('attachment_saved')<failedRead.events.indexOf('identity_exception')));
  const failedLinks=await capture({linkFailure:true});
  check(()=>assert.match(failedLinks.error,/junction_write_unverified/));
  check(()=>assert(failedLinks.events.indexOf('attachment_saved')<failedLinks.events.indexOf('identity_exception')));
  const missingReport={Participants:items([part('keep@example.test')])};
  let stopped=false;try{await run('Report Capture Identity Exceptions',[],missingReport);}catch(e){stopped=/resolution_incomplete/.test(e.message);}
  check(()=>assert(stopped));
  console.log(JSON.stringify({node_checks:checks,postgres_envelope_parity:Boolean(dbEnvelopes),result:'PASS'}));
})().catch(e=>{console.error(e.stack);process.exit(1);});
"""


def source_checks():
    w = json.loads(CAPTURE.read_text())
    reverse = json.loads(REVERSE.read_text())
    nodes = {n['name']: n for n in w['nodes']}
    assert w['active'] is False
    assert w['settings']['executionOrder'] == 'v1'
    assert len({tuple(n['position']) for n in w['nodes']}) == len(w['nodes']), 'overlapping node positions'
    edges = w['connections']['Create Interaction']['main'][0]
    assert [e['node'] for e in edges] == ['Participants', 'Merge Participants', 'Build Attachments', 'Report Capture Identity Exceptions']
    positions = [nodes[e['node']]['position'][1] for e in edges]
    assert positions == sorted(set(positions)), 'Diagnostic must remain last in v1'
    assert nodes['If']['parameters']['conditions']['conditions'][0]['operator']['operation'] == 'notEquals'
    assert nodes['If']['parameters']['conditions']['conditions'][0]['rightValue'] == 'create'
    assert nodes['Merge Participants']['type'] == 'n8n-nodes-base.code'
    assert w['connections']['If']['main'][0] == []
    assert 'Create Contacts' not in w['connections']
    for name in ['Match Contact','Recheck Contact Identities','Create Contacts']:
        n = nodes[name]
        assert n['retryOnFail'] is False
        assert n['onError'] == 'continueRegularOutput'
        assert n['parameters']['options']['response']['response'] == {
            'fullResponse':True,'neverError':True,'responseFormat':'json'}
        assert n['parameters']['options']['redirect']['redirect']['followRedirects'] is False
    assert nodes['Recheck Contact Identities']['executeOnce'] is True
    assert nodes['Report Capture Identity Exceptions'].get('onError','stopWorkflow') == 'stopWorkflow'
    for workflow in [w, reverse]:
        assert not workflow.get('pinData') and not workflow.get('staticData') and not workflow.get('meta')
    assert reverse['active'] is False and len(reverse['nodes']) == 9
    # Preserve all unrelated original behavior, credentials bindings, and every
    # attachment connection; this comparison fails if the seven-file scope drifts.
    baseline = lambda path: json.loads(subprocess.check_output(['git','show',f'{BASE}:{path}'],cwd=ROOT,text=True))
    old = baseline('n8n-workflows/capture-email-contacts.json')
    # Reviewer export abstractions must never be mistaken for committed values.
    prior_participants = next(n for n in old['nodes'] if n['name']=='Participants')
    allowlist = lambda code: ast.literal_eval(re.search(r"const mine\s*=\s*(?:new Set\()?([\[][\s\S]*?[\]])", code).group(1))
    assert allowlist(nodes['Participants']['parameters']['jsCode']) == allowlist(prior_participants['parameters']['jsCode'])
    editable = {'Participants','Match Contact','Resolve','If','Create Contacts','Merge Participants','Build Junction Rows'}
    for n in old['nodes']:
        if n['name'] not in editable: assert nodes[n['name']] == n, n['name']+' drifted'
    changed_edges = {'Create Interaction','If','Create Contacts','Merge Participants','Build Junction Rows'}
    for name, value in old['connections'].items():
        if name not in changed_edges: assert w['connections'][name] == value
    old_reverse = baseline('n8n-workflows/clickup-contact-review-supabase-reverse.json')
    for key in ['nodes','connections','settings']: assert reverse[key] == old_reverse[key]
    print('PASS: exact graph order, retry policy, inactive reverse, scope and private-export checks')


def node_checks(envelopes=None):
    result = subprocess.run([shutil.which('node') or 'node','-e',NODE_TESTS],
        input=json.dumps({'workflow':json.loads(CAPTURE.read_text()),
                          'fixture':json.loads(FIXTURE.read_text()),'envelopes':envelopes}),
        text=True,capture_output=True,timeout=60)
    print(result.stdout, end='')
    if result.returncode: raise AssertionError(result.stderr)


def postgres_checks(guard_path):
    docker = shutil.which('docker') or '/usr/local/bin/docker'
    container = subprocess.check_output([docker,'run','--pull=never','--rm','-d','--network=none',
        '--read-only','--tmpfs','/var/lib/postgresql/data','--tmpfs','/var/run/postgresql',
        '--tmpfs','/tmp','-e','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE],text=True).strip()
    def sql(source,check=True):
        r = subprocess.run([docker,'exec','-i',container,'psql','-X','-U','postgres','-At','-v','ON_ERROR_STOP=1'],
            input=source,text=True,capture_output=True,timeout=30)
        if check and r.returncode: raise AssertionError(r.stderr)
        return r
    def quote(s): return "'" + s.replace("'","''") + "'"
    try:
        for _ in range(80):
            ready = subprocess.run([docker,'exec',container,'pg_isready','-U','postgres'],capture_output=True)
            proc = subprocess.run([docker,'exec',container,'cat','/proc/1/comm'],capture_output=True,text=True)
            if ready.returncode == 0 and proc.stdout.strip() == 'postgres': break
            time.sleep(.25)
        else: raise AssertionError('PostgreSQL readiness timed out')
        sql('''CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
CREATE TABLE public.contacts(id uuid PRIMARY KEY, emails text[], merged_into uuid,
 review_status text, relationship_tier integer, updated_at timestamptz);
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts FORCE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON public.contacts TO service_role;
CREATE TABLE interaction_note_contacts(note_id uuid,contact_id uuid,PRIMARY KEY(note_id,contact_id));''')
        fixture = json.loads(FIXTURE.read_text())
        for c in fixture['contacts']:
            sql('INSERT INTO public.contacts SELECT * FROM jsonb_populate_record(NULL::public.contacts,'+quote(json.dumps(c))+'::jsonb);')
        original = sql('SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM contacts c;').stdout
        migration = (ROOT/'scripts/sql/crm-lookup-email-identities.sql').read_text()
        sql(migration)
        sql(migration)  # replace is idempotent, grants stay narrow
        assert sql("SELECT proconfig,prosecdef,provolatile FROM pg_proc WHERE oid='public.crm_lookup_email_identities(text[])'::regprocedure;").stdout.strip() == '{"search_path=pg_catalog, public"}|f|s'
        for role in ['anon','authenticated']:
            r = sql(f"SET ROLE {role}; SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test']);",check=False)
            assert r.returncode and 'permission denied for function' in r.stderr
        sql('CREATE ROLE synthetic_restricted; GRANT EXECUTE ON FUNCTION public.crm_lookup_email_identities(text[]) TO synthetic_restricted;')
        r = sql("SET ROLE synthetic_restricted; SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test']);",check=False)
        assert r.returncode and 'crm_identity_lookup_visibility_unverified' in r.stderr, 'non-bypass role must fail closed'
        sql('GRANT SELECT ON contacts TO synthetic_restricted;')
        r = sql("SET ROLE synthetic_restricted; SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test']);",check=False)
        assert r.returncode and 'crm_identity_lookup_visibility_unverified' in r.stderr, 'RLS cannot masquerade as new identity'
        sql('CREATE ROLE synthetic_bypass BYPASSRLS; GRANT EXECUTE ON FUNCTION public.crm_lookup_email_identities(text[]) TO synthetic_bypass;')
        r = sql("SET ROLE synthetic_bypass; SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test']);",check=False)
        assert r.returncode and 'permission denied for table contacts' in r.stderr, 'invoker still requires SELECT'
        sql('ALTER ROLE service_role NOBYPASSRLS;')
        r = sql("SET ROLE service_role; SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test']);",check=False)
        assert r.returncode and 'crm_identity_lookup_visibility_unverified' in r.stderr
        sql('ALTER ROLE service_role BYPASSRLS;')
        for invalid in ['NULL',"ARRAY[NULL]::text[]", "ARRAY['']", "array_fill('x@example.test'::text,ARRAY[1001])"]:
            assert sql('SELECT public.crm_lookup_email_identities('+invalid+');',check=False).returncode
        boundary = sql("SELECT public.crm_lookup_email_identities(ARRAY(SELECT 'boundary-'||g||'@example.test' FROM generate_series(1,1000) g));")
        assert len(json.loads(boundary.stdout)['identities']) == 1000
        envelopes = {}
        for c in fixture['cases']:
            r = sql('SET ROLE service_role; SELECT public.crm_lookup_email_identities(ARRAY['+quote(c['email'])+']);')
            envelopes[c['name']] = json.loads(r.stdout.splitlines()[-1])
        assert sql('SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM contacts c;').stdout == original, 'lookup mutated contacts'
        r = sql("SELECT public.crm_lookup_email_identities(ARRAY[]::text[]);")
        assert json.loads(r.stdout)['identities'] == []
        r = sql("SELECT public.crm_lookup_email_identities(ARRAY['keep@example.test',' KEEP@example.test ']);")
        assert len(json.loads(r.stdout)['identities']) == 1
        node_checks(envelopes)
        sql("""INSERT INTO contacts(id,emails,merged_into,review_status)
SELECT ('00000000-0000-0000-0000-'||lpad((10000+g)::text,12,'0'))::uuid,
 CASE WHEN g=1 THEN ARRAY['long-chain@example.test'] ELSE ARRAY[]::text[] END,
 CASE WHEN g<101 THEN ('00000000-0000-0000-0000-'||lpad((10001+g)::text,12,'0'))::uuid ELSE NULL END,
 CASE WHEN g<101 THEN 'merged' ELSE 'kept' END FROM generate_series(1,101) g;""")
        chain = json.loads(sql("SELECT public.crm_lookup_email_identities(ARRAY['long-chain@example.test']);").stdout)
        assert chain['identities'][0]['owners'][0]['resolution'] == 'depth_limit'
        sql("""INSERT INTO contacts(id,emails,review_status)
SELECT ('00000000-0000-0000-0000-'||lpad((20000+g)::text,12,'0'))::uuid,
 ARRAY['many-owners@example.test'],'kept' FROM generate_series(1,1005) g;""")
        many = json.loads(sql("SELECT public.crm_lookup_email_identities(ARRAY['many-owners@example.test']);").stdout)
        assert len(many['identities'][0]['owners']) == 1005, 'scalar result must retain every owner'
        # Fresh SQL snapshots after a real uncommitted insert: lookup cannot
        # infer absence is a safe create lock. The guard is a deploy dependency.
        if guard_path:
            guard = pathlib.Path(guard_path).read_bytes()
            assert hashlib.sha256(guard).hexdigest() == GUARD_SHA256, 'unreviewed guard dependency'
            sql(guard.decode())
        first = subprocess.Popen([docker,'exec','-i',container,'psql','-X','-U','postgres','-v','ON_ERROR_STOP=1'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first.stdin.write("BEGIN; INSERT INTO contacts(id,emails,review_status) VALUES('00000000-0000-0000-0000-000000001001',ARRAY['race@example.test'],'unscreened'); SELECT pg_advisory_xact_lock(87654321); SELECT pg_sleep(2); COMMIT;\n")
        first.stdin.close()
        for _ in range(80):
            if sql("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND objid=87654321 AND granted;").stdout.strip()=='1': break
            time.sleep(.025)
        else: raise AssertionError('first transaction failed to start')
        assert json.loads(sql("SELECT public.crm_lookup_email_identities(ARRAY['race@example.test']);").stdout)['identities'][0]['owners'] == []
        second = sql("\\set VERBOSITY verbose\nINSERT INTO contacts(id,emails,review_status) VALUES('00000000-0000-0000-0000-000000001002',ARRAY['RACE@example.test'],'unscreened');",check=False)
        first.wait(timeout=10)
        assert first.returncode == 0
        owners = json.loads(sql("SELECT public.crm_lookup_email_identities(ARRAY['race@example.test']);").stdout)['identities'][0]['owners']
        if guard_path:
            assert second.returncode and 'CRM01' in second.stderr and 'crm_known_email_identity:' in second.stderr
            print('PASS: hash-bound reviewed guard emitted SQLSTATE CRM01 and exact crm_known_email_identity: message prefix')
            assert len(owners)==1 and owners[0]['resolution']=='ok'
        else:
            assert second.returncode==0 and len(owners)==2, 'unguarded racing owners must both be returned'
        sql("INSERT INTO interaction_note_contacts VALUES('00000000-0000-0000-0000-000000002001','00000000-0000-0000-0000-000000001001');")
        duplicate = sql("INSERT INTO interaction_note_contacts VALUES('00000000-0000-0000-0000-000000002001','00000000-0000-0000-0000-000000001001');",check=False)
        assert duplicate.returncode and 'duplicate key' in duplicate.stderr
        assert sql('SELECT count(*) FROM interaction_note_contacts;').stdout.strip()=='1'
        print('PASS: real PostgreSQL lookup parity, role grants/RLS, immutability, concurrent identity snapshots, unique junctions; guard='+str(bool(guard_path)))
    finally:
        subprocess.run([docker,'rm','-f',container],check=True,capture_output=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--postgres',action='store_true')
    parser.add_argument('--insert-guard',help='Optional exact previously reviewed guard; never live SQL')
    args=parser.parse_args()
    if args.insert_guard and not args.postgres: parser.error('--insert-guard requires --postgres')
    source_checks()
    node_checks()
    if args.postgres: postgres_checks(args.insert_guard)


if __name__ == '__main__': main()
