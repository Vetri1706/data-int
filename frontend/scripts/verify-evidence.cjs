// UI integration tests with explicitly mocked API data, not a live scraping benchmark.
(async () => {
  const { default: assert } = await import("node:assert/strict");
  const { pathToFileURL } = await import("node:url");
  const modulePath = process.env.PLAYWRIGHT_MODULE;
  const { chromium } = await import(modulePath ? pathToFileURL(`${modulePath}/index.mjs`).href : "playwright");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const id="11111111-1111-4111-8111-111111111111", ds="22222222-2222-4222-8222-222222222222", runId="33333333-3333-4333-8333-333333333333";
    const time="2026-09-29T10:00:00Z";
    const collection={id,title:"Evidence regression fixture",prompt:"Find companies",status:"completed",updated_at:time,data_contract:{entity_type:"company",fields:[{name:"location",required:true}],constraints:[]}};
    const run={id:runId,collection_id:id,status:"completed",records_verified:1,current_stage:"finalizing",started_at:time,completed_at:time,steps:[]};
    const dataset={id:ds,run_id:runId,collection_id:id,name:"Saved historical version",created_at:time,record_count:1,schema:{verification_method:"typed-claims-v1"}};
    const evidence={field_name:"location",state:"supported",verbatim_quote:"Fixture Robotics is based in Chennai.",extracted_value:"Chennai",source_url:"https://example.com/evidence",char_start:100,char_end:136};
    const record={id:"fixture-record",canonical_name:"Fixture Robotics",status:"verified",confidence_score:null,
      primary_attributes:{location:"Chennai",claims:{location:{state:"supported",value:"Chennai",reason:"Explicit location relation",evidence:[evidence]}},
        verification:{accepted:true,version:"typed-claims-v1",field_coverage:1,acceptance_failures:[]},provenance:{source_urls:[evidence.source_url],field_evidence:[evidence]}}};
    let fail=false, posted=null, cancelled=0, emptyDataset=false;
    const history={data:[{id:1,type:"stage.updated",created_at:time,payload:{stage:"extracting",actual_event:"Persisted extraction event"}}],review_candidates:[]};
    await page.route("**/v1/**",async route=>{
      const path=new URL(route.request().url()).pathname.replace(/^\/api/,"");
      const method=route.request().method();
      let data;
      if(path==="/v1/auth/me") data={id:"fixture-user",name:"Fixture User",email:"fixture@example.test"};
      else if(path==="/v1/me/models") data={default:{provider:"local",model:"qwen2.5-coder:1.5b-instruct",allow_external:false},providers:[{id:"local",label:"Ollama",available:true,models:[{id:"qwen2.5-coder:1.5b-instruct",label:"Fixture local model",available:true}]}]};
      else if(path==="/v1/me/source-discovery") data={domains:[{domain:"example.com",pages:[{title:"Fixture source",url:"https://example.com/evidence",provider:"fixture"}]}],total:1};
      else if(path==="/v1/collections" && method==="POST") {posted=route.request().postDataJSON();collection.status="running";run.status="running";data=collection;}
      else if(path===`/v1/collections/${id}/run`) data={run_id:runId,status:"pending"};
      else if(path===`/v1/runs/${runId}/cancel`) {cancelled++;run.status="cancelled";collection.status="cancelled";data={status:"cancelled",worker_notified:true};}
      else if(path==="/v1/collections") data={data:[collection]};
      else if(path===`/v1/collections/${id}`) data=collection;
      else if(path===`/v1/collections/${id}/runs`) data={data:[run]};
      else if(path===`/v1/runs/${runId}`) data=run;
      else if(path===`/v1/runs/${runId}/history`) data=history;
      else if(path==="/v1/datasets") data={data:emptyDataset?[]:[{...dataset,id:"newer-dataset",name:"Newer version",created_at:"2026-09-30T12:00:00Z",run_id:"newer-run"},dataset]};
      else if(path===`/v1/datasets/${ds}`) data=dataset;
      else if(path===`/v1/datasets/${ds}/records`) data={data:[record]};
      else if(path==="/v1/sources") data={data:[{id:"s",domain:"example.com",source_type:"general",enabled:true,extraction_success_rate:null}]};
      else data={};
      const status=fail && path!=="/v1/auth/me" ? 503 : 200;
      await route.fulfill({status,contentType:"application/json",body:JSON.stringify(status===503?{error:"Fixture API unavailable"}:data)});
    });
    const base=process.env.VERIFY_BASE_URL||"http://127.0.0.1:3107";
    await page.goto(`${base}/collections/${id}`);
    await page.getByRole("button",{name:"Fixture Robotics",exact:true}).click();
    const drawer=page.getByRole("dialog");
    await drawer.waitFor();
    const text=await drawer.innerText();
    assert(text.includes("location: supported"));assert(text.includes("100% of requested fields supported"));
    assert(text.includes("Retrieval status unknown"));assert(!text.includes("200 OK"));assert(text.includes("Source text characters 100"));
    await page.getByRole("button",{name:"Close evidence drawer"}).click();
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
    await page.setViewportSize({width:1440,height:900});
    await page.goto(`${base}/datasets/${ds}`);
    await page.getByRole("heading",{name:"Saved historical version"}).waitFor();
    assert.equal(await page.getByRole("button",{name:"Fixture Robotics",exact:true}).count(),1);
    assert((await page.getByRole("link",{name:"Export this version as CSV"}).getAttribute("href")).includes(ds));
    assert(!page.url().includes("/collections/"));
    await page.goto(`${base}/history`);
    const link=page.getByRole("link",{name:"Evidence regression fixture",exact:true});
    await link.waitFor();assert.equal(await link.getAttribute("href"),`/runs/${runId}`);
    await link.click();await page.getByText(/Persisted extraction event/).waitFor();
    // A historical exhausted run can have fetched pages but no accepted dataset.
    emptyDataset=true;collection.status="exhausted";run.status="exhausted";run.records_verified=0;
    const stopReason="Local Ollama (deepseek-r1:1.5b): inference timed out.";
    history.data.push({id:2,type:"run.exhausted",created_at:time,payload:{reason:stopReason,sources:[
      {url:"https://example.com/a",title:"Retrieved supplier page",http_status:200,fetched_at:time},
      {url:"https://example.com/b",title:"Retrieved catalogue page",http_status:200,fetched_at:time}]}});
    history.review_candidates.push({...record.primary_attributes,canonical_name:"Unverified Supplier",accepted:false});
    await page.goto(`${base}/collections/${id}`);
    await page.getByText(stopReason,{exact:true}).waitFor();
    await page.getByText("No verified results",{exact:true}).waitFor();
    await page.getByRole("heading",{name:"No accepted records yet"}).waitFor();
    assert.equal(await page.getByText("No records match these filters.",{exact:true}).count(),0);
    await page.getByRole("button",{name:"Inspect source pages"}).click();
    await page.getByText("Retrieved supplier page",{exact:true}).waitFor();
    assert.equal(await page.getByText("HTTP 200",{exact:true}).count(),2);
    const frame=await page.locator('.app-frame').evaluate(el=>({x:el.getBoundingClientRect().x,y:el.getBoundingClientRect().y,width:el.getBoundingClientRect().width,viewport:document.documentElement.clientWidth,radius:getComputedStyle(el).borderRadius,shadow:getComputedStyle(el).boxShadow}));
    assert.equal(frame.x,0);assert.equal(frame.y,0);assert.equal(frame.width,frame.viewport);assert.equal(frame.radius,'0px');assert.equal(frame.shadow,'none');
    assert.equal(await page.locator('aside svg rect[fill="#102D4F"]').count(),1);
    await page.screenshot({path:'../.runtime/workspace-updated.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
    await page.getByRole('button',{name:'Open navigation'}).click();
    await page.getByRole('navigation',{name:'Workspace'}).getByRole('link',{name:'Overview',exact:true}).waitFor();
    await page.getByRole('button',{name:'Close navigation',exact:true}).first().click();
    await page.setViewportSize({width:1440,height:900});
    emptyDataset=false;history.review_candidates=[];
    // Template supplies actual prompt/fields; permission is required before run.
    await page.goto(`${base}/collections/new?template=wf-tech-hiring`);
    assert((await page.getByLabel("Collection requirement").inputValue()).includes("20 current backend"));
    await page.getByLabel("Limit search to domains (optional)").fill("example.com");
    await page.getByRole("button",{name:"Continue",exact:true}).click();
    await page.getByText(/job_url \(url\)/).waitFor();
    await page.getByLabel(/I have permission/).check();
    await page.getByRole("button",{name:"Run collection",exact:true}).click();
    await page.getByRole("button",{name:"Cancel run",exact:true}).waitFor();
    assert.equal(posted.template_contract.entity_type,"job");assert.equal(posted.template_contract.target_count,20);
    assert.deepEqual(posted.source_policy.approved_domains,["example.com"]);
    await page.getByRole("button",{name:"Cancel run",exact:true}).click();
    await page.getByRole("alert").filter({hasText:/cancelled/i}).waitFor({timeout:10000});assert.equal(cancelled,1);
    fail=true;
    await page.goto(`${base}/collections/${id}`);await page.getByRole("alert").filter({hasText:"Fixture API unavailable"}).waitFor();
    assert.equal(await page.getByRole("button",{name:"Fixture Robotics",exact:true}).count(),0);
    assert.deepEqual(errors,[]);
    console.log("PASS: claim states, unknown metrics, exact dataset version, stored run history, template payload, permission gate, real cancellation request, mobile width and API errors");
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
