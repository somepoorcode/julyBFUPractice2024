import requests


def vk_api_request(screen_name, access_token):
    response = requests.get('https://api.vk.com/method/users.get', params={
        'user_ids': screen_name,
        'access_token': access_token,
        'v': '5.199'
    })
    data = response.json()
    if 'response' in data:
        return data['response'][0]['id']
    else:
        return ''


def get_user_id(user_id):
    access_token = open('access_token.txt', 'r').readline()
    if user_id.startswith("id"):
        return user_id[2:]
    else:
        try:
            user_id = vk_api_request(user_id, access_token)
            return str(user_id)
        except ValueError as e:
            print(e)
            return ''
