// Runs in Qt's isolated ApplicationWorld, sharing DOM and cookies with Pixiv.
// The page's scripts cannot call the Python bridge or read its CSRF token.
(() => {
    const origin = __PBB_ORIGIN__;
    if (location.origin !== origin || window.top !== window) return;
    let csrf = '';
    let bridge;

    function parseIdentity(doc) {
        const meta = doc.querySelector('#meta-global-data');
        if (meta) {
            const data = JSON.parse(meta.content);
            if (data.userData && data.userData.id && data.token)
                return { user: data.userData, token: data.token };
        }
        const next = doc.querySelector('#__NEXT_DATA__');
        if (next) {
            const props = JSON.parse(next.textContent).props?.pageProps;
            if (props?.gaUserData?.login && props.serverSerializedPreloadedState) {
                const state = JSON.parse(props.serverSerializedPreloadedState);
                if (state.userData?.self && state.api?.token)
                    return { user: state.userData.self, token: state.api.token };
            }
        }
        return null;
    }

    async function fetchChecked(path, options) {
        const url = new URL(path, origin);
        if (url.origin !== origin) throw { message: '请求域名不匹配', fatal: true };
        const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options });
        if (!response.ok) throw { message: `Pixiv 请求失败（HTTP ${response.status}）`, status: response.status };
        if (new URL(response.url).origin !== origin)
            throw { message: '登录已失效，请重新登录', status: 401 };
        return response;
    }

    async function jsonResponse(response) {
        let data;
        try { data = await response.json(); }
        catch (_) { throw { message: '接口未返回 JSON，请检查登录或验证页面', fatal: true }; }
        if (!data || typeof data !== 'object' || Array.isArray(data) || typeof data.error !== 'boolean')
            throw { message: '接口响应格式变化', fatal: true };
        return data;
    }

    window.pbbRequest = async (id, request, timeout) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout);
        try {
            if (location.origin !== origin) throw { message: '请先返回 Pixiv 首页', status: 401 };
            const options = { method: request.method, signal: controller.signal,
                              headers: { 'Accept': 'application/json' } };
            let data;
            if (request.response_type === 'session') {
                csrf = '';
                let identity = parseIdentity(document);
                if (!identity) {
                    const response = await fetchChecked('/request', options);
                    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
                    identity = parseIdentity(doc);
                }
                if (!identity || !/^[1-9][0-9]*$/.test(String(identity.user.id)))
                    throw { message: '尚未登录 Pixiv，请在登录窗口完成登录', status: 401 };
                const checked = await jsonResponse(await fetchChecked('/ajax/user/extra', options));
                if (checked.error) throw { message: '登录会话不可用，请重新登录', status: 401 };
                csrf = identity.token;
                data = { error: false, body: { userId: String(identity.user.id),
                         name: identity.user.name || identity.user.account || String(identity.user.id) } };
            } else {
                if (request.method === 'POST') {
                    if (!csrf) throw { message: '缺少登录凭证，请刷新登录状态', status: 401 };
                    options.headers['X-CSRF-TOKEN'] = csrf;
                    options.headers['Content-Type'] = request.encoding === 'form'
                        ? 'application/x-www-form-urlencoded; charset=utf-8'
                        : 'application/json; charset=utf-8';
                    options.body = request.encoding === 'form'
                        ? new URLSearchParams(request.data).toString() : JSON.stringify(request.data);
                }
                const response = await fetchChecked(request.path, options);
                if (request.response_type === 'bookmark_metadata') {
                    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
                    const tag = doc.querySelector('.bookmark-detail-unit input[name="tag"]');
                    if (!tag) throw { message: '无法读取原收藏标签，保留原收藏' };
                    const comment = doc.querySelector('textarea[name="comment"], input[name="comment"]');
                    if (!comment) throw { message: '无法读取原收藏备注，保留原收藏' };
                    data = { error: false, body: { tags: tag.value.split(/\s+/).filter(Boolean),
                                                 comment: comment.value } };
                } else data = await jsonResponse(response);
            }
            bridge.reply(id, JSON.stringify({ response: data }));
        } catch (error) {
            bridge.reply(id, JSON.stringify({ error: {
                message: error.name === 'AbortError' ? '请求超时，正在检查最终状态' : (error.message || '网络请求失败'),
                status: error.status || 0, fatal: !!error.fatal } }));
        } finally { clearTimeout(timer); }
    };

    new QWebChannel(qt.webChannelTransport, channel => {
        bridge = channel.objects.pbbBridge;
        bridge.reply('__ready__', '{}');
    });
})();
