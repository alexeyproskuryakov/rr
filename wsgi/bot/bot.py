import urlparse
from collections import defaultdict
from datetime import datetime
from lxml import html
from multiprocessing import Lock, Queue
import praw
from praw.objects import MoreComments
import random
import re
import requests
import requests.auth
import time

from wsgi import properties
from wsgi.db import DBHandler
from wsgi.engine import net_tryings

re_url = re.compile("((https?|ftp)://|www\.)[^\s/$.?#].[^\s]*")

log = properties.logger.getChild("reddit-bot")

A_POST = "post"
A_VOTE = "vote"
A_COMMENT = "comment"

DEFAULT_LIMIT = 100

min_copy_count = 2
min_comment_create_time_difference = 3600 * 24 * 30 * 2
min_comment_ups = 20
max_comment_ups = 100000
min_donor_num_comments = 50
min_selection_comments = 10
max_selection_comments = 20

check_comment_text = lambda text: not re_url.match(text) and len(text) > 15 and len(text) < 120
post_info = lambda post: {"fullname": post.fullname, "url": post.url}

db = DBHandler()

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36"

USER_AGENTS = [
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0; chromeframe/12.0.742.112)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0; .NET CLR 2.0.50727; SLCC2; .NET CLR 3.5.30729; .NET CLR 3.0.30729; Media Center PC 6.0; Zune 4.0; Tablet PC 2.0; InfoPath.3; .NET4.0C; .NET4.0E)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; ru; rv:1.9.1.2) Gecko/20090729 Firefox/3.5.2",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; SHC-KIOSK; SHC-Mac-5FE3; SHC-Unit-K0816; SHC-KMT; .NET C",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; Trident/4.0; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; InfoPath",
    "Mozilla/5.0 (iPad; U; CPU OS 3_2 like Mac OS X; en-us) AppleWebKit/531.21.10 (KHTML, like Gecko) Version/4.0.4 Mobile/7B",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; .NET CLR 2.0.50727)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/5.0 (webOS/1.4.3; U; en-US) AppleWebKit/532.2 (KHTML, like Gecko) Version/1.0 Safari/532.2 Pixi/1.1",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/533.16 (KHTML, like Gecko) Version/5.0 Safari/533.16",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.4) Gecko/20100611 Firefox/3.6.4 GTB7.0",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
]


def _so_long(created, min_time):
    return (datetime.utcnow() - datetime.fromtimestamp(created)).total_seconds() > min_time


class ActionsHandler(object):
    def __init__(self):
        self.last_actions = {
            A_POST: datetime.utcnow(),
            A_VOTE: datetime.utcnow(),
            A_COMMENT: datetime.utcnow(),
        }
        self.acted = defaultdict(set)
        self.info = {}

    def set_action(self, action_name, identity, info=None):
        self.last_actions[action_name] = datetime.utcnow()
        self.acted[action_name].add(identity)
        if info:
            to_save = {'action': action_name, "r_id": identity, "info": info}
            db.bot_log.insert_one(to_save)
            self.info[identity] = info

    def get_last_action(self, action_name):
        res = self.last_actions.get(action_name)
        if not res:
            raise Exception("Action %s is not supported")
        return res

    def is_acted(self, action_name, identity):
        return identity in self.acted[action_name]

    def get_actions(self, action_name=None):
        return self.acted if action_name is None else self.acted.get(action_name)

    def get_action_info(self, identity):
        action_info = self.info.get(identity)
        return action_info


class loginsProvider(object):
    def __init__(self, login=None, logins_list=None):
        """
        :param login: must be {"time of lat use":{login:<login>, password:<pwd>, User-Agent:<some user agent>}}
        """
        self.last_time = datetime.now()
        self.logins = login or {
            self.last_time: {'login': "4ikist", "password": "sederfes", "User-Agent": DEFAULT_USER_AGENT}}
        if logins_list and isinstance(logins_list, list):
            self.add_logins(logins_list)
        self.ensure_times()
        self.current_login = self.get_early_login()
        db.save_reddit_login(self.current_login.get("login"), self.current_login.get("password"))
        db.update_reddit_login("4ikist", {"User-Agent": DEFAULT_USER_AGENT, "last_use": time.time()})

    def ensure_times(self):
        self._times = dict(map(lambda el: (el[1]['login'], el[0]), self.logins.items()))

    def get_early_login(self):
        previous_time = self.last_time
        self.last_time = datetime.now()
        next_login = self.logins.pop(previous_time)
        self.logins[self.last_time] = next_login
        self.ensure_times()
        self.current_login = self.logins[min(self.logins.keys())]
        return self.current_login

    def add_logins(self, logins):
        for login in logins:
            self.logins[datetime.now()] = login
        self.ensure_times()

    def get_login_times(self):
        return self._times

    @net_tryings
    def check_current_login(self):
        res = requests.get(
                "http://cors-anywhere.herokuapp.com/www.reddit.com/user/%s/about.json" % self.current_login.get(
                        "login"),
                headers={"origin": "http://www.reddit.com"})
        if res.status_code != 200:
            log.error("Check login is err :( ,%s " % res)


class RedditBot(object):
    def __init__(self, subreddits, user_agent=None):
        self.last_actions = ActionsHandler()

        self.mutex = Lock()
        self.subreddits = subreddits
        self._current_subreddit = None

        self.low_copies_posts = set()

        self.subscribed_subreddits = set()
        self.friends = set()

        self.reddit = praw.Reddit(user_agent=user_agent or "Reddit search bot")

    def get_hot_and_new(self, subreddit_name, sort=None):
        subreddit = self.reddit.get_subreddit(subreddit_name)
        hot = list(subreddit.get_hot(limit=DEFAULT_LIMIT))
        new = list(subreddit.get_new(limit=DEFAULT_LIMIT))
        hot_d = dict(map(lambda x: (x.fullname, x), hot))
        new_d = dict(map(lambda x: (x.fullname, x), new))
        hot_d.update(new_d)
        log.info("Will search for dest posts candidates at %s posts" % len(hot_d))
        result = hot_d.values()
        if sort:
            result.sort(cmp=sort)
        return result

    @property
    def current_subreddit(self):
        self.mutex.acquire()
        result = self._current_subreddit
        self.mutex.release()
        return result

    @current_subreddit.setter
    def current_subreddit(self, new_sbrdt):
        self.mutex.acquire()
        self._current_subreddit = new_sbrdt
        self.mutex.release()

    @property
    def login(self):
        self.mutex.acquire()
        result = self._login.get("login")
        self.mutex.release()
        return result


class RedditReadBot(RedditBot):
    def __init__(self, subreddits, user_agent=None):
        super(RedditReadBot, self).__init__(subreddits, user_agent)

    def find_comment(self, at_subreddit=None):
        get_comment_authors = lambda post_comments: set(
                map(lambda comment: comment.author.name if not isinstance(comment,
                                                                          MoreComments) and comment.author else "",
                    post_comments)
        )  # function for retrieving authors from post comments

        def cmp_by_created_utc(x, y):
            result = x.created_utc - y.created_utc
            if result > 0.5:
                return 1
            elif result < 0.5:
                return -1
            else:
                return 0

        used_subreddits = set()

        while 1:
            subreddit = at_subreddit or random.choice(self.subreddits)
            if subreddit in used_subreddits:
                continue
            else:
                used_subreddits.add(subreddit)

            self.current_subreddit = subreddit
            all_posts = self.get_hot_and_new(subreddit, sort=cmp_by_created_utc)
            for post in all_posts:
                if self.last_actions.is_acted(A_COMMENT, post.fullname) or post.url in self.low_copies_posts:
                    continue
                copies = self._get_post_copies(post)
                copies = filter(lambda copy: _so_long(copy.created_utc, min_comment_create_time_difference) and \
                                             copy.num_comments > min_donor_num_comments,
                                copies)
                if len(copies) > min_copy_count:
                    post_comments = set(self._get_all_post_comments(post))
                    post_comments_authors = get_comment_authors(post_comments)
                    copies.sort(cmp=cmp_by_created_utc)
                    for copy in copies:
                        if copy.fullname != post.fullname and copy.subreddit != post.subreddit:
                            comment = self._retrieve_interested_comment(copy, post_comments_authors)
                            if comment and comment not in set(map(
                                    lambda x: x.body if not isinstance(x, MoreComments) else "",
                                    post_comments
                            )):
                                log.info("comment: [%s] \nin post [%s] at subreddit [%s]" % (
                                    comment, post.fullname, subreddit))
                                return post.fullname, comment
                else:
                    self.low_copies_posts.add(post.url)

    def _get_post_copies(self, post):
        copies = list(self.reddit.search("url:'/%s'/" % post.url))
        log.debug("found %s copies by url: %s" % (len(copies), post.url))
        return list(copies)

    def _retrieve_interested_comment(self, copy, post_comment_authors):
        # prepare comments from donor to selection
        comments = []
        for i, comment in enumerate(copy.comments):
            if isinstance(comment, MoreComments):
                try:
                    comments.extend(comment.comments())
                except Exception as e:
                    log.exception(e)
                    log.warning("Fuck. Some error. More comment were not unwind. ")
            if i < random.randint(min_selection_comments, max_selection_comments):
                continue
            comments.append(comment)

        for comment in comments:
            author = comment.author
            if author and comment.ups >= min_comment_ups and comment.ups <= max_comment_ups and check_comment_text(
                    comment.body):
                return comment.body

    def _get_all_post_comments(self, post, filter_func=lambda x: x):
        result = []
        for comment in post.comments:
            if isinstance(comment, MoreComments):
                result.extend(filter(filter_func, comment.comments()))
            else:
                result.append(filter_func(comment))
        return result


class RedditWriteBot(RedditBot):
    def __init__(self, subreddits, login_credentials):
        """
        :param subreddits: subbreddits which this bot will comment
        :param login_credentials:  dict object with this attributes: client_id, client_secret, redirect_url, access_token, refresh_token, login and password of user and user_agent 
         user agent can not present it will use some default user agent
        :return:
        """
        super(RedditWriteBot, self).__init__(subreddits)

        self.r_caf = 0
        self.r_cur = 0
        self.ss = 0

        self.c_read_post = 0
        self.c_vote_comment = 0
        self.c_comment_post = 0

        self.action_function_params = {}
        self.init_work_cycle()
        self.init_engine(login_credentials)
        log.info("Write bot inited with params \n %s" % (login_credentials))

    def init_engine(self, login_credentials):
        user_agent = login_credentials.get("user_agent", random.choice(USER_AGENTS))
        r = praw.Reddit(user_agent)
        r.set_oauth_app_info(login_credentials['client_id'], login_credentials['client_secret'], login_credentials['redirect_uri'])
        r.set_access_credentials(**login_credentials.get("info"))
        r.login(login_credentials["user"],login_credentials["pwd"])
        self.reddit = r

    def init_work_cycle(self):
        consuming = random.randint(70, 90)
        production = 100 - consuming

        prod_voting = random.randint(60, 95)
        prod_commenting = 100 - prod_voting

        production_voting = (prod_voting * production) / 100
        production_commenting = (prod_commenting * production) / 100

        self.action_function_params = {"consume": consuming, "vote": production_voting,
                                       "comment": production_commenting}

    def can_do(self, action):
        """
        Action
        :param action: can be: [vote, comment, consume]
        :return:  true or false
        """

        summ = self.c_vote_comment + self.c_comment_post + self.c_read_post
        interested_count = 0
        if action == "vote":
            interested_count = self.c_vote_comment
        elif action == "comment":
            interested_count = self.c_comment_post
        elif action == "consume":
            interested_count = self.c_read_post

        granted_perc = self.action_function_params.get(action)
        current_perc = int(((float(summ) if summ else 1.0) / (interested_count if interested_count else 100.0)) * 100)

        return current_perc <= granted_perc

    def process_work_cycle(self, subreddit_name, url_for_video):
        pass

    def do_see_post(self, post, subscribe=9, author_friend=9, comments=7, comment_vote=8,
                    comment_friend=7, post_vote=6, max_wait_time=30):
        """
        1) go to his url with yours useragent, wait random
        2) random check comments and random check more comments
        3) random go to link in comments
        :param post:
        :return:
        """
        try:
            res = requests.get(post.url, headers={"User-Agent": self._login.get("User-Agent")})
            log.info("SEE POST result: %s" % res)
        except Exception as e:
            log.warning("Can not see post %s url %s \n:(" % (post.fullname, post.url))
        wt = random.randint(1, max_wait_time)
        log.info("wait time: %s" % wt)
        time.sleep(wt)
        if post_vote and random.randint(0, 10) > post_vote and self.can_do("vote"):
            vote_count = random.choice([1, -1])
            post.vote(vote_count)

        if comments and random.randint(0, 10) > comments and wt > 5:  # go to post comments
            for comment in post.comments:
                if comment_vote and random.randint(0, 10) >= comment_vote and self.can_do("vote"):  # voting comment
                    vote_count = random.choice([1, -1])
                    comment.vote(vote_count)
                    self.c_vote_comment += 1
                    if comment_friend and random.randint(0,
                                                         10) >= comment_friend and vote_count > 0:  # friend comment author
                        c_author = comment.author
                        if c_author.name not in self.friends:
                            c_author.friend()
                            self.friends.add(c_author.name)

                if random.randint(0, 10) >= 8:  # go to url in comment
                    urls = re_url.findall(comment.body)
                    for url in urls:
                        res = requests.get(url, headers={"User-Agent": self._login.get("User-Agent")})
                        log.info("SEE Comment link result: %s", res)
                        self.r_cur += 1

        if subscribe and random.randint(0, 10) >= subscribe and \
                        post.subreddit.display_name not in self.subscribed_subreddits:  # subscribe sbrdt
            self.reddit.subscribe(post.subreddit.display_name)
            self.subscribed_subreddits.add(post.subreddit.display_name)
            self.ss += 1

        if author_friend and random.randint(0,
                                            10) >= author_friend and post.author.fullname not in self.friends:  # friend post author
            post.author.friend()
            self.friends.add(post.author.fullname)
            self.r_caf += 1

        self.c_read_post += 1

    def _get_random_near(self, slice, index, max):
        rnd = lambda x: random.randint(x / 10, x / 2) or 1
        max_ = lambda x: x if x < max and max_ != -1  else max
        count_random_left = max_(rnd(len(slice[0:index])))
        count_random_right = max_(rnd(len(slice[index:])))

        return [random.choice(slice[0:index]) for _ in xrange(count_random_left)], \
               [random.choice(slice[index:]) for _ in xrange(count_random_right)]

    def do_comment_post(self, post_fullname, subreddit_name, comment_text, max_post_near=3, max_wait_time=20, **kwargs):
        near_posts = self.get_hot_and_new(subreddit_name)
        for i, _post in enumerate(near_posts):
            if _post.fullname == post_fullname:
                see_left, see_right = self._get_random_near(near_posts, i, random.randint(1, 4))
                for p_ind in see_left:
                    self.do_see_post(p_ind, max_wait_time=max_wait_time, **kwargs)

                for comment in filter(lambda comment: isinstance(comment, MoreComments), _post.comments):
                    etc = comment.comments()
                    print etc
                    if random.randint(0, 10) > 6:
                        break

                _post.add_comment(comment_text)

                for p_ind in see_right:
                    self.do_see_post(p_ind, max_wait_time=max_wait_time, **kwargs)

        if random.randint(0, 10) > 7 and subreddit_name not in self.subscribed_subreddits:
            self.reddit.subscribe(subreddit_name)

    def is_shadowbanned(self):
        self.mutex.acquire()
        result = self.login_provider.check_current_login()
        self.mutex.release()
        return result


if __name__ == '__main__':
    db = DBHandler()
    sbrdt = "videos"
    rbot = RedditReadBot(["videos"])
    # """client_id: O5AZrYjXI1R-7g
    # """client_secret: LOsmYChS2dcdQIlkMG9peFR6Lns
    wbot = RedditWriteBot(["videos"], db.get_access_credentials("Shlak2k15"))

    subreddit = "videos"
    log.info("start found comment...")
    # post_fullname, text = rbot.find_comment(subreddit)
    post_fullname, text = "t3_400kke", "[Fade Into You](http://www.youtube.com/watch?v=XucegAHZojc)"#rbot.find_comment(subreddit)
    log.info("fullname: %s\ntext: %s"%(post_fullname, text))
    wbot.do_comment_post(post_fullname, subreddit, text, max_wait_time=2, subscribe=0, author_friend=0, comments=0,
                         comment_vote=0, comment_friend=0, post_vote=0, )