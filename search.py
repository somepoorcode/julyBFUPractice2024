import json
import aiohttp
import asyncio
import datetime as dt
from get_id import get_user_id
from aiolimiter import AsyncLimiter
from database import factory, User, Comment

ACCESS_TOKEN = open('access_token.txt', 'r').readline()
API_VERSION = '5.199'
LIMITER = AsyncLimiter(3, 0.15)

session_db = factory()


async def vk_api_request(session, method, params):
    async with LIMITER:
        url = f'https://api.vk.com/method/' + method
        params.update({
            'access_token': ACCESS_TOKEN,
            'v': API_VERSION
        })

        async with session.get(url, params=params) as response:
            data = await response.json()
            if 'error' in data:
                error_code = data['error']['error_code']
                if error_code == 5:  # access error
                    return False
                if error_code == 6:  # too many requests per second
                    await asyncio.sleep(1)
                    return await vk_api_request(session, method, params)
                else:
                    print("error " + str(data['error']))
                    return False
            return data.get('response', False)


async def execute_batch(session, api_method, params_list):
    results = []
    for i in range(0, len(params_list), 25):
        batch = params_list[i:i + 25]
        code = '''
        var params_list = ''' + json.dumps(batch) + ''';
        var result = [];
        var i = 0;
        while (i < params_list.length) {
            result.push(API.''' + api_method + '''(params_list[i]));
            i = i + 1;
        }
        return result;
        '''

        response = await vk_api_request(session, 'execute', {'code': code})
        if response and isinstance(response, list):
            results.extend(response)
        else:
            print("error when trying to execute batch for " + api_method)
    return results


async def get_posts(session, owner_id):
    params_list = [{"owner_id": owner_id, "count": 50, "extended": 1}]
    return await execute_batch(session, 'wall.get', params_list)


async def get_comments(session, owner_id, post_ids, comment_id=None):
    if comment_id:
        params_list = [{"owner_id": owner_id, "comment_id": comment_id, "count": 50}]
    else:
        params_list = [{"owner_id": owner_id, "post_id": post_id, "count": 50} for post_id in post_ids]
    return await execute_batch(session, 'wall.getComments', params_list)


async def get_photo_comments(session, owner_id):
    params_list = [{"owner_id": owner_id, "count": 50, "extended": 1}]
    return await execute_batch(session, 'photos.getAllComments', params_list)


async def is_profile_open(session, user_id):
    response = await vk_api_request(session, 'users.get', {'user_ids': user_id, 'fields': 'is_closed'})
    if response and isinstance(response, list):
        return not response[0].get('is_closed', False)
    return False


async def is_group_open(session, group_id):
    response = await vk_api_request(session, 'groups.getById', {'group_id': group_id, 'fields': 'is_closed'})
    if response and isinstance(response, dict):
        groups = response.get('groups', [])
        if groups and isinstance(groups, list):
            return groups[0].get('is_closed') == 0
    return False


async def get_friends(session, user_id):
    response = await vk_api_request(session, 'friends.get', {'user_id': user_id, 'fields': 'can_access_closed'})
    if response and isinstance(response, dict):
        return [friend['id'] for friend in response['items'] if friend.get('can_access_closed', False)]
    return []


async def get_groups(session, user_id):
    response = await vk_api_request(session, 'groups.get', {'user_id': user_id, 'extended': 1})
    if response and isinstance(response, dict):
        return [group['id'] for group in response['items'] if group.get('is_closed', 1) == 0]
    return []


async def search_comments(session, user_id, target_user_id):
    all_comments = []
    photo_ids = set()

    posts_response = await get_posts(session, user_id)
    if posts_response:
        for response in posts_response:
            if not response:
                continue
            posts = response.get('items', [])
            post_ids = [post.get('id') for post in posts if post.get('id')]
            for post in posts:
                if 'attachments' in post:
                    for attachment in post['attachments']:
                        if attachment['type'] == 'photo':
                            photo_ids.add(attachment['photo']['id'])
            if post_ids:
                comments_response = await get_comments(session, user_id, post_ids)
                if comments_response:
                    for comment_response in comments_response:
                        if not comment_response:
                            continue
                        comments = comment_response.get('items', [])
                        for comment in comments:
                            if comment['from_id'] == int(target_user_id) and comment['text'] != '':
                                all_comments.append({
                                    'text': comment['text'],
                                    'owner_id': comment.get('owner_id', user_id),
                                    'post_id': comment['post_id'],
                                    'creation_date': str(comment['date'])
                                })

                            if 'thread' in comment and comment['thread']['count'] > 0 and 'post_id' in comment:
                                replies_response = await get_comments(session, user_id, [comment['post_id']],
                                                                      comment_id=comment['id'])
                                if replies_response:
                                    for reply_response in replies_response:
                                        if not reply_response:
                                            continue
                                        replies = reply_response.get('items', [])
                                        for reply in replies:
                                            if reply['from_id'] == int(target_user_id) and reply['text'] != '':
                                                all_comments.append({
                                                    'text': reply['text'],
                                                    'owner_id': reply.get('owner_id', user_id),
                                                    'post_id': comment['post_id'],
                                                    'creation_date': str(reply['date'])
                                                })

    photo_comments_response = await get_photo_comments(session, user_id)
    if photo_comments_response:
        for response in photo_comments_response:
            if not response:
                continue
            comments = response.get('items', [])
            for comment in comments:
                if comment['from_id'] == int(target_user_id) and comment['text'] != '':
                    if comment['pid'] not in photo_ids:
                        all_comments.append({
                            'text': comment['text'],
                            'owner_id': comment.get('owner_id', user_id),
                            'photo_id': comment['pid'],
                            'creation_date': str(comment['date'])
                        })

    return all_comments


async def main(user_id):
    user_id = get_user_id(user_id)
    if not user_id:
        return "invalid id"

    comments_count = 0
    async with aiohttp.ClientSession() as session:
        if not await is_profile_open(session, user_id):
            user = session_db.query(User).filter_by(user_id=user_id).first()
            if user:
                user.is_profile_open = 0
                user.search_date = int(dt.datetime.now().timestamp())
                user.mood_id = 0
            else:
                session_db.add(User(
                    user_id=user_id,
                    is_profile_open=0,
                    comments_count=0,
                    search_date=int(dt.datetime.now().timestamp()),
                    mood_id=0
                ))
            session_db.commit()
            return "profile is closed"
        else:
            print("search started")
            comments = []

            comments += await search_comments(session, user_id, user_id)
            print("searched targets page")
            await asyncio.sleep(1)

            friends = await get_friends(session, user_id)
            for i in range(0, len(friends), 25):
                batch_friends = friends[i:i + 25]
                tasks = [search_comments(session, friend_id, user_id) for friend_id in batch_friends if
                         await is_profile_open(session, friend_id)]
                results = await asyncio.gather(*tasks)
                for result in results:
                    comments.extend(result)
            print("searched targets friends")
            await asyncio.sleep(1)

            groups = await get_groups(session, user_id)
            for i in range(0, len(groups), 25):
                batch_groups = groups[i:i + 25]
                tasks = [search_comments(session, f'-{group_id}', user_id) for group_id in batch_groups if
                         await is_group_open(session, group_id)]
                results = await asyncio.gather(*tasks)
                for result in results:
                    comments.extend(result)
            print("searched targets groups")

            user = session_db.query(User).filter_by(user_id=user_id).first()
            if user:
                user.is_profile_open = 1
                user.search_date = int(dt.datetime.now().timestamp())
                user.mood_id = 0
            else:
                session_db.add(User(
                    user_id=user_id,
                    is_profile_open=1,
                    comments_count=0,
                    search_date=int(dt.datetime.now().timestamp()),
                    mood_id=0
                ))

            if comments:
                existing_comments = {(comment.text, str(comment.creation_date)) for comment in
                                     session_db.query(Comment).filter_by(sender_id=user_id)}
                new_comments = [comment for comment in comments if
                                (comment['text'], comment['creation_date']) not in existing_comments]

                max_comment_id = session_db.query(Comment.comment_id).order_by(Comment.comment_id.desc()).first()
                if max_comment_id:
                    comment_id = max_comment_id[0] + 1
                else:
                    comment_id = 0

                for comment in new_comments:
                    session_db.add(Comment(
                        comment_id=comment_id,
                        text=comment['text'],
                        sender_id=user_id,
                        receiver_id=comment['owner_id'],
                        type='wall' if 'post_id' in comment else 'photo',
                        type_id=comment['post_id'] if 'post_id' in comment else comment['photo_id'],
                        mood_id=0,
                        creation_date=int(comment['creation_date'])
                    ))
                    comment_id += 1
                    comments_count += 1
                    print(comment)
                session_db.commit()

            user = session_db.query(User).filter_by(user_id=user_id).first()
            if user:
                user.comments_count += comments_count
                session_db.commit()

            return "search finished"


def find_comments(target_id):
    return asyncio.run(main(target_id))
