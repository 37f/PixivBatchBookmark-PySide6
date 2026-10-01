"""Qt-independent workflow. Requests are yielded, never blindly retried."""

from dataclasses import dataclass, field
from typing import Generator


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0, stop_batch: bool = False):
        super().__init__(message)
        self.status = status
        self.stop_batch = stop_batch or status in (401, 403, 429)


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    data: dict = field(default_factory=dict)
    encoding: str = 'json'
    response_type: str = 'json'


@dataclass(frozen=True)
class BookmarkState:
    bookmark_id: str | None
    private: bool | None
    stop_batch: bool = False


@dataclass(frozen=True)
class ItemResult:
    illust_id: str
    status: str
    message: str
    stop_batch: bool = False


Flow = Generator[Request, dict, ItemResult]


class BookmarkService:
    def _request(self, request):
        reply = yield request
        if not isinstance(reply, dict) or not isinstance(reply.get('error'), bool):
            raise ApiError('Pixiv 响应格式变化，已停止任务', stop_batch=True)
        if reply['error']:
            raise ApiError(str(reply.get('message') or 'Pixiv 拒绝请求'))
        return reply.get('body')

    def _state(self, illust_id):
        body = yield from self._request(Request('GET', f'/ajax/illust/{illust_id}'))
        if not isinstance(body, dict) or 'bookmarkData' not in body:
            raise ApiError('作品响应缺少 bookmarkData，状态无法确认', stop_batch=True)
        if 'id' in body and str(body['id']) != illust_id:
            raise ApiError('作品响应 ID 不匹配', stop_batch=True)
        value = body['bookmarkData']
        if value is None:
            return BookmarkState(None, None)
        if (not isinstance(value, dict) or not isinstance(value.get('private'), bool)
                or not str(value.get('id', '')).isdigit() or int(value['id']) <= 0):
            raise ApiError('收藏状态格式变化，状态无法确认', stop_batch=True)
        return BookmarkState(str(value['id']), value['private'])

    def _metadata(self, illust_id):
        body = yield from self._request(Request('GET',
            f'/bookmark_add.php?type=illust&illust_id={illust_id}', response_type='bookmark_metadata'))
        if (not isinstance(body, dict) or not isinstance(body.get('tags'), list)
                or any(not isinstance(tag, str) for tag in body['tags'])
                or not isinstance(body.get('comment'), str)):
            raise ApiError('无法读取原收藏标签/备注，保留原收藏')
        return body

    @staticmethod
    def _add(illust_id, private, metadata):
        return Request('POST', '/ajax/illusts/bookmarks/add', {
            'illust_id': illust_id, 'restrict': int(private),
            'tags': metadata['tags'], 'comment': metadata['comment']})

    @staticmethod
    def _delete(state):
        return Request('POST', '/ajax/illusts/bookmarks/delete',
                       {'bookmark_id': state.bookmark_id}, encoding='form')

    def _mutate_and_check(self, request, illust_id, wanted):
        write_error = None
        try:
            yield from self._request(request)
        except ApiError as error:
            write_error = error
        # A POST can reach the server even if its response is lost. Read first.
        try:
            state = yield from self._state(illust_id)
        except ApiError as error:
            raise ApiError('写入后状态无法确认，请人工检查该作品：' + str(error),
                           status=error.status, stop_batch=True) from error
        if state.private == wanted:
            return BookmarkState(state.bookmark_id, state.private,
                                 bool(write_error and write_error.stop_batch))
        if write_error:
            raise write_error
        raise ApiError('写入后核验失败，作品未达到目标收藏状态')

    def apply_one(self, illust_id: str, action: str, private: bool) -> Flow:
        if action not in ('bookmark', 'remove') or not illust_id.isdigit() or int(illust_id) <= 0:
            raise ValueError('Invalid artwork ID or action')
        try:
            original = yield from self._state(illust_id)
            if action == 'remove':
                if original.bookmark_id is None:
                    return ItemResult(illust_id, 'skipped', '未收藏，已跳过')
                confirmed = yield from self._mutate_and_check(self._delete(original), illust_id, None)
                return ItemResult(illust_id, 'success', '已取消收藏并核验', confirmed.stop_batch)

            mode = '私密' if private else '公开'
            if original.private == private:
                return ItemResult(illust_id, 'skipped', f'已是{mode}收藏，已跳过')
            if original.bookmark_id is None:
                confirmed = yield from self._mutate_and_check(self._add(illust_id, private,
                    {'tags': [], 'comment': ''}), illust_id, private)
                return ItemResult(illust_id, 'success', f'已{mode}收藏并核验', confirmed.stop_batch)

            metadata = yield from self._metadata(illust_id)
            # Never delete before the original metadata has been captured.
            removed = yield from self._mutate_and_check(self._delete(original), illust_id, None)
            try:
                if removed.stop_batch:
                    raise ApiError('取消阶段触发访问限制，先恢复原收藏再停止', stop_batch=True)
                confirmed = yield from self._mutate_and_check(self._add(illust_id, private, metadata), illust_id, private)
                return ItemResult(illust_id, 'success', f'已转换为{mode}收藏并核验', confirmed.stop_batch)
            except ApiError as conversion_error:
                if conversion_error.stop_batch:
                    # Read still must precede recovery when the last state is unknown.
                    try:
                        current = yield from self._state(illust_id)
                    except ApiError:
                        raise ApiError('转换失败，当前状态无法确认，请人工检查', stop_batch=True)
                    if current.private == private:
                        return ItemResult(illust_id, 'success', f'已转换为{mode}收藏并核验', True)
                    if current.bookmark_id is not None:
                        return ItemResult(illust_id, 'failed', '转换失败，保留当前收藏：' + str(conversion_error), True)
                # _mutate_and_check already read an unbookmarked state on ordinary failure.
                try:
                    restored = yield from self._mutate_and_check(self._add(illust_id, original.private, metadata),
                                                                 illust_id, original.private)
                except ApiError as restore_error:
                    raise ApiError('转换失败且恢复未完成，请人工检查：' + str(restore_error), stop_batch=True)
                return ItemResult(illust_id, 'failed', '转换失败，已恢复原收藏：' + str(conversion_error),
                                  conversion_error.stop_batch or restored.stop_batch)
        except ApiError as error:
            return ItemResult(illust_id, 'failed', str(error), error.stop_batch)
