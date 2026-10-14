using System.Net;
using System.Text;
using System.Text.Json;
using PixivBatchBookmark.Core;

var tests = new List<(string Name, Func<Task> Run)>();
void Test(string name, Action test) => tests.Add((name, () => { test(); return Task.CompletedTask; }));
void AsyncTest(string name, Func<Task> test) => tests.Add((name, test));
void Equal<T>(T expected, T actual) { if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new Exception($"Expected {expected}; actual {actual}"); }
void True(bool value) { if (!value) throw new Exception("Expected true"); }
void Ids(string input, string expected) => Equal(expected, string.Join(",", IdParser.Parse(input).Ids));

Test("pure IDs keep input order", () => Ids("97003966\n103816477 97720788", "97003966,103816477,97720788"));
Test("artwork URL extracts artwork only", () => Ids("https://www.pixiv.net/en/artworks/97003966?user_id=12345", "97003966"));
Test("legacy URL extracts illust_id", () => Ids("https://www.pixiv.net/member_illust.php?mode=medium&illust_id=103816477", "103816477"));
Test("labeled prose ignores title numbers", () => Ids("2026作品- pixiv id：97003966\n今天冷…-pixiv ID:103816477", "97003966,103816477"));
Test("duplicates counted and removed", () => { var p=IdParser.Parse("97003966\n97003966\nhttps://pixiv.net/artworks/97003966"); Equal(1,p.Ids.Count); Equal(2,p.DuplicateCount); });
Test("reject user novel foreign URLs and unlabeled prose", () => { var p=IdParser.Parse("https://www.pixiv.net/users/97003966\nhttps://www.pixiv.net/novel/show.php?id=97003966\nhttps://evil.test/artworks/97003966\n作品 97003966\n2026-10-01"); Equal(0,p.Ids.Count); Equal(5,p.IgnoredLines.Count); });
Test("leading zero normalizes without accepting zero", () => Ids("000097003966, 0", "97003966"));
Test("short numeric artwork ID is valid", () => Ids("1", "1"));
Test("overflow ID is rejected", () => Ids("9999999999999999999999999999999", ""));
Test("mixed URLs retain order and no bare digits from URLs", () => Ids("https://pixiv.net/artworks/103816477 https://pixiv.net/artworks/97003966", "103816477,97003966"));
Test("scheme-less Pixiv URL", () => Ids("www.pixiv.net/artworks/97003966", "97003966"));
Test("numbered artwork link never submits list number", () => Ids("1 https://www.pixiv.net/artworks/97003966", "97003966"));
Test("artwork link suffix never becomes artwork", () => Ids("https://www.pixiv.net/artworks/97003966 2026", "97003966"));
Test("numbers beside excluded URLs are not IDs", () => Ids("2026 https://www.pixiv.net/users/97003966\n1 https://evil.test/97720788\n123 https://www.pixiv.net/novel/show.php?id=97003966", ""));

foreach (var mode in new[]{BookmarkMode.Public,BookmarkMode.Private})
{
    AsyncTest($"new {mode} bookmark is verified", async () => { var c=new MemoryClient(); var r=await new BookmarkService(c).ProcessAsync("97003966",BatchAction.Bookmark,mode,default); Equal(ItemStatus.Success,r.Status); Equal(mode,c.State.Mode); True(c.Reads>=2); });
    AsyncTest($"existing {mode} bookmark is untouched", async () => { var c=new MemoryClient(mode); var r=await new BookmarkService(c).ProcessAsync("97003966",BatchAction.Bookmark,mode,default); Equal(ItemStatus.Skipped,r.Status); Equal(0,c.Writes); Equal("old",c.State.BookmarkId); });
    AsyncTest($"conversion from {mode} removes then recreates and preserves tags", async () => { var target=mode==BookmarkMode.Public?BookmarkMode.Private:BookmarkMode.Public; var c=new MemoryClient(mode); var r=await new BookmarkService(c).ProcessAsync("97003966",BatchAction.Bookmark,target,default); Equal(ItemStatus.Success,r.Status); Equal(target,c.State.Mode); Equal("delete,add",string.Join(",",c.Mutations)); Equal("风景,收藏",string.Join(",",c.Details.Tags)); Equal("note",c.Details.Comment); });
    AsyncTest($"remove {mode} bookmark is verified", async () => { var c=new MemoryClient(mode); var r=await new BookmarkService(c).ProcessAsync("97003966",BatchAction.Remove,mode,default); Equal(ItemStatus.Success,r.Status); True(!c.State.IsBookmarked); True(c.Reads>=2); });
}
AsyncTest("remove missing bookmark skips", async () => { var c=new MemoryClient(); var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Remove,BookmarkMode.Public,default); Equal(ItemStatus.Skipped,r.Status); Equal(0,c.Writes); });
AsyncTest("failed target add restores old private bookmark", async () => { var c=new MemoryClient(BookmarkMode.Private){FailAdds=1}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Public,default); Equal(ItemStatus.Failed,r.Status); Equal(BookmarkMode.Private,c.State.Mode); Equal("风景,收藏",string.Join(",",c.Details.Tags)); });
AsyncTest("rollback failure stops batch", async () => { var c=new MemoryClient(BookmarkMode.Private){FailAdds=2}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Public,default); Equal(ItemStatus.Failed,r.Status); True(r.StopBatch); True(!c.State.IsBookmarked); });
AsyncTest("details failure happens before deletion", async () => { var c=new MemoryClient(BookmarkMode.Private){FailDetails=true}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Public,default); Equal(ItemStatus.Failed,r.Status); Equal(0,c.Writes); Equal(BookmarkMode.Private,c.State.Mode); });
AsyncTest("delete acknowledgment with unchanged state fails safely", async () => { var c=new MemoryClient(BookmarkMode.Private){IgnoreRemove=true}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Public,default); Equal(ItemStatus.Failed,r.Status); True(r.StopBatch); Equal(BookmarkMode.Private,c.State.Mode); });
AsyncTest("late add acknowledgment does not cause duplicate mutation", async () => { var c=new MemoryClient(BookmarkMode.Private){AddThenThrow=true}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Public,default); Equal(ItemStatus.Success,r.Status); Equal(BookmarkMode.Public,c.State.Mode); Equal(2,c.Writes); });
AsyncTest("cancel before item prevents mutations", async () => { var c=new MemoryClient(BookmarkMode.Public); using var cancel=new CancellationTokenSource(); cancel.Cancel(); try {await new BookmarkService(c).ProcessAsync("1",BatchAction.Remove,BookmarkMode.Public,cancel.Token); throw new Exception("Expected cancellation");} catch(OperationCanceledException) { Equal(0,c.Writes); } });
AsyncTest("stop during conversion finishes current item", async () => { using var cancel=new CancellationTokenSource(); var c=new MemoryClient(BookmarkMode.Public){OnRemove=cancel.Cancel}; var r=await new BookmarkService(c).ProcessAsync("1",BatchAction.Bookmark,BookmarkMode.Private,cancel.Token); Equal(ItemStatus.Success,r.Status); Equal(BookmarkMode.Private,c.State.Mode); });

const string global="<meta content='{&quot;token&quot;:&quot;abc123&quot;,&quot;userData&quot;:{&quot;id&quot;:&quot;42&quot;,&quot;name&quot;:&quot;测试&quot;}}' name='global-data'>";
Test("HTML escaped global data authenticates", () => {var s=SessionParser.Parse(global); Equal("42",s.UserId); Equal("abc123",s.CsrfToken); Equal("测试",s.UserName);});
Test("JSON string wrapped global data authenticates", () => {var data=JsonSerializer.Serialize("{\"token\":\"xyz123\",\"userData\":{\"id\":\"42\",\"name\":\"T\"}}"); Equal("xyz123",SessionParser.Parse($"<meta name='global-data' content='{WebUtility.HtmlEncode(data)}'>").CsrfToken);});
Test("missing login identity blocks authentication", () => {try {SessionParser.Parse("<meta name='global-data' content='{\"token\":\"abc\",\"userData\":null}'>"); throw new Exception("Expected auth failure");} catch(PixivException e){ True(e.StopBatch); }});
// Current homepage shape, with identity and token replaced by test values.
const string nextState="{\"api\":{\"token\":\"next123\",\"language\":\"zh\"},\"userData\":{\"self\":{\"id\":\"42\",\"name\":\"测试 & 收藏\"},\"users\":{\"99\":{\"id\":\"99\",\"name\":\"其他作者\"}}}}";
string NextPage(string state, bool loggedIn=true) => "<script type='application/json' id='__NEXT_DATA__'>" + JsonSerializer.Serialize(new { props=new { pageProps=new { isLoggedIn=loggedIn, serverSerializedPreloadedState=state } } }) + "</script>";
void RejectSession(string html) {try {SessionParser.Parse(html); throw new Exception("Expected auth failure");} catch(PixivException e){True(e.StopBatch);}}
Test("Next homepage authenticates the current user with its API token", () => {var s=SessionParser.Parse(NextPage(nextState)); Equal("42",s.UserId); Equal("next123",s.CsrfToken); Equal("测试 & 收藏",s.UserName);});
Test("unusable legacy metadata falls back to current homepage data", () => Equal("42",SessionParser.Parse("<meta name='global-data' content='{\"userData\":null}'>"+NextPage(nextState)).UserId));
Test("Next logged-out page cannot authenticate cached self data", () => RejectSession(NextPage(nextState,false)));
Test("other users on Next page cannot replace missing self identity", () => RejectSession(NextPage(nextState.Replace("\"self\":{\"id\":\"42\",\"name\":\"测试 & 收藏\"}","\"self\":null"))));
Test("Next identity without token cannot authenticate", () => RejectSession(NextPage(nextState.Replace("\"token\":\"next123\",",""))));
Test("malformed Next state fails closed", () => RejectSession(NextPage("not-json")));
Test("bookmark form preserves entity decoded tags and comment", () => {var d=SessionParser.ParseBookmarkDetails("<form><input value='风景 A&amp;B' name='tag'><input name=\"comment\" value=\"hello &amp; world\"></form>"); Equal("风景,A&B",string.Join(",",d.Tags)); Equal("hello & world",d.Comment);});
Test("missing bookmark form blocks conversion", () => {try {SessionParser.ParseBookmarkDetails("<html>login</html>"); throw new Exception("Expected parse failure");} catch(PixivException) {} });

async Task WithHttp(Func<HttpRequestMessage,Task<HttpResponseMessage>> handler, Func<PixivHttpClient,Task> run, bool serveIdentity=true)
{using var http=new HttpClient(new FixtureHandler(r=>serveIdentity && r.RequestUri!.AbsolutePath=="/" ? Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(global)}) : handler(r))){BaseAddress=new Uri("https://www.pixiv.net/")}; await run(new PixivHttpClient(http,new("42","T","csrf123")));}
HttpResponseMessage Json(string json, HttpStatusCode status=HttpStatusCode.OK) => new(status){Content=new StringContent(json,Encoding.UTF8,"application/json")};
AsyncTest("GET reads private bookmark state", () => WithHttp(r=>Task.FromResult(Json("{\"error\":false,\"body\":{\"bookmarkData\":{\"id\":\"765\",\"private\":true}}}")),async c=>{var s=await c.GetStateAsync("1",default); Equal("765",s.BookmarkId); Equal(BookmarkMode.Private,s.Mode);}));
AsyncTest("null bookmark means missing", () => WithHttp(r=>Task.FromResult(Json("{\"error\":false,\"body\":{\"bookmarkData\":null}}")),async c=>True(!(await c.GetStateAsync("1",default)).IsBookmarked)));
AsyncTest("missing bookmark field is not mistaken for missing bookmark", () => WithHttp(r=>Task.FromResult(Json("{\"error\":false,\"body\":{}}")),async c=>{try {await c.GetStateAsync("1",default); throw new Exception("Expected schema failure");} catch(PixivException e){True(e.StopBatch);}}));
AsyncTest("ADD sends target privacy tags CSRF and artwork referer", () => WithHttp(async r=>{Equal("/ajax/illusts/bookmarks/add",r.RequestUri!.AbsolutePath); Equal("application/json",r.Content!.Headers.ContentType!.MediaType); Equal("csrf123",r.Headers.GetValues("x-csrf-token").Single()); Equal("https://www.pixiv.net/artworks/1",r.Headers.Referrer!.AbsoluteUri); var b=JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement; Equal("1",b.GetProperty("illust_id").GetString()); Equal(1,b.GetProperty("restrict").GetInt32()); Equal("tag",b.GetProperty("tags")[0].GetString()); return Json("{\"error\":false,\"body\":{}}");},c=>c.AddAsync("1",BookmarkMode.Private,new(["tag"]),default)));
AsyncTest("DELETE uses bookmark ID form", () => WithHttp(async r=>{Equal("/ajax/illusts/bookmarks/delete",r.RequestUri!.AbsolutePath); Equal("bookmark_id=765",await r.Content!.ReadAsStringAsync()); Equal("application/x-www-form-urlencoded",r.Content.Headers.ContentType!.MediaType); return Json("{\"error\":false,\"body\":null}");},c=>c.RemoveAsync("765",default)));
foreach(var status in new[]{HttpStatusCode.Unauthorized,HttpStatusCode.Forbidden,HttpStatusCode.TooManyRequests,HttpStatusCode.ServiceUnavailable})
    AsyncTest($"HTTP {(int)status} stops batch",()=>WithHttp(r=>Task.FromResult(Json("{}",status)),async c=>{try{await c.GetStateAsync("1",default); throw new Exception("Expected HTTP failure");}catch(PixivException e){True(e.StopBatch);}}));
AsyncTest("404 may skip unavailable work and continue",()=>WithHttp(r=>Task.FromResult(Json("{}",HttpStatusCode.NotFound)),async c=>{try{await c.GetStateAsync("1",default); throw new Exception("Expected unavailable");}catch(PixivException e){True(!e.StopBatch);}}));
AsyncTest("HTML challenge page stops batch",()=>WithHttp(r=>Task.FromResult(Json("<html>challenge</html>")),async c=>{try{await c.GetStateAsync("1",default); throw new Exception("Expected non JSON failure");}catch(PixivException e){True(e.StopBatch);}}));
AsyncTest("anonymous null bookmark state cannot verify removal",()=>WithHttp(r=>Task.FromResult(r.RequestUri!.AbsolutePath=="/"?new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent("<meta name='global-data' content='{\"token\":\"abc\",\"userData\":null}'>")}:Json("{\"error\":false,\"body\":{\"bookmarkData\":null}}")),async c=>{try{await c.GetStateAsync("1",default); throw new Exception("Expected identity failure");}catch(PixivException e){True(e.StopBatch);}},false));
AsyncTest("wrong account null state cannot verify removal",()=>WithHttp(r=>Task.FromResult(r.RequestUri!.AbsolutePath=="/"?new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(global.Replace("42","43"))}:Json("{\"error\":false,\"body\":{\"bookmarkData\":null}}")),async c=>{try{await c.GetStateAsync("1",default); throw new Exception("Expected account mismatch");}catch(PixivException e){True(e.StopBatch);}},false));
foreach(var authStatus in new[]{HttpStatusCode.Unauthorized,HttpStatusCode.Forbidden})
    AsyncTest($"delete {(int)authStatus} cannot be relabeled success by anonymous state", async ()=>
    {
        var stateReads=0;
        await WithHttp(r=>Task.FromResult(r.Method==HttpMethod.Post?Json("{}",authStatus):Json(++stateReads==1?"{\"error\":false,\"body\":{\"bookmarkData\":{\"id\":\"765\",\"private\":true}}}":"{\"error\":false,\"body\":{\"bookmarkData\":null}}")),async c=>
        {var result=await new BookmarkService(c).ProcessAsync("1",BatchAction.Remove,BookmarkMode.Private,default); Equal(ItemStatus.Failed,result.Status); True(result.StopBatch);});
    });

var failed=0;
foreach(var (name,run) in tests){try{await run(); Console.WriteLine($"PASS {name}");}catch(Exception e){failed++; Console.WriteLine($"FAIL {name}: {e.Message}");}}
Console.WriteLine($"Tests: {tests.Count}; passed: {tests.Count-failed}; failed: {failed}");
return failed==0?0:1;

// External Pixiv is represented by an in-memory state model. Assertions check final
// bookmark state as well as write ordering, so a wrong mode or missing rollback fails.
sealed class MemoryClient : IPixivClient
{
    public BookmarkState State; public BookmarkDetails Details=new(["风景","收藏"],"note");
    public int Writes,Reads,FailAdds; public bool FailDetails,IgnoreRemove,AddThenThrow;
    public Action? OnRemove; public List<string> Mutations=[];
    public MemoryClient(BookmarkMode? mode=null){State=mode is null?BookmarkState.None:new("old",mode);}
    public Task<BookmarkState> GetStateAsync(string id,CancellationToken ct){ct.ThrowIfCancellationRequested(); Reads++; return Task.FromResult(State);}
    public Task<BookmarkDetails> GetDetailsAsync(string id,CancellationToken ct){if(FailDetails)throw new PixivException("details unavailable"); return Task.FromResult(Details);}
    public Task RemoveAsync(string id,CancellationToken ct){ct.ThrowIfCancellationRequested(); Writes++; Mutations.Add("delete"); if(!IgnoreRemove)State=BookmarkState.None; OnRemove?.Invoke(); return Task.CompletedTask;}
    public Task AddAsync(string id,BookmarkMode mode,BookmarkDetails details,CancellationToken ct){ct.ThrowIfCancellationRequested(); Writes++; Mutations.Add("add"); if(FailAdds-->0)throw new PixivException("add failed"); State=new("new",mode); Details=details; if(AddThenThrow)throw new PixivException("response lost"); return Task.CompletedTask;}
}
sealed class FixtureHandler(Func<HttpRequestMessage,Task<HttpResponseMessage>> handler):HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>handler(request);
}
