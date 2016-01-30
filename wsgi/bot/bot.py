# coding=utf-8
import traceback

from datetime import datetime

from multiprocessing.process import Process
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from threading import Thread

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

log = properties.logger.getChild("bot")

A_POST = "post"
A_VOTE = "vote"
A_COMMENT = "comment"
A_CONSUME = "consume"

A_SUBSCRIBE = "subscribe"
A_FRIEND = "friend"

S_BAN = "ban"
S_WORK = "work"
S_SLEEP = "sleep"
S_UNKNOWN = "unknown"

DEFAULT_LIMIT = 100
DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT = 60 * 60

min_copy_count = 2
min_comment_create_time_difference = 3600 * 24 * 10

shift_copy_comments_part = 5  # общее количество комментариев / это число  = сколько будет пропускаться
min_donor_comment_ups = 3
max_donor_comment_ups = 100000
min_donor_num_comments = 50

max_consuming = 90
min_consuming = 70

min_voting = 65
max_voting = 95

check_comment_text = lambda text: not re_url.match(text) and len(text) > 15 and len(text) < 120 and "Edit" not in text

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


@net_tryings
def check_any_login(login):
    res = requests.get(
            "http://www.reddit.com/user/%s/about.json" % login,
            headers={"origin": "http://www.reddit.com",
                     "User-Agent": random.choice(USER_AGENTS)})
    if res.status_code != 200:
        return False
    if res.json().get("error", None):
        return False
    return True


def _so_long(created, min_time):
    return (datetime.utcnow() - datetime.fromtimestamp(created)).total_seconds() > min_time


class BotConfiguration(object):
    def __init__(self, data=None):
        """
        Configuration of bot live
        :return:
        """
        if not data:
            self.subscribe = 9
            self.author_friend = 9
            self.comments = 7
            self.comment_mwt = 5
            self.comment_vote = 8
            self.comment_friend = 9
            self.comment_url = 8
            self.post_vote = 6
            self.max_wait_time = 30

            self.max_post_near_commented = 50
            self.subscribe_subreddit = 7
        elif isinstance(data, dict):
            for k, v in data.iteritems():
                self.__dict__[k] = int(v)

    def set(self, conf_name, conf_val):
        if conf_name in self.__dict__:
            self.__dict__[conf_name] = conf_val

    @property
    def data(self):
        return self.__dict__


class RedditBot(object):
    def __init__(self, user_agent=None):
        self.reddit = praw.Reddit(user_agent=user_agent or random.choice(USER_AGENTS))

    def get_hot_and_new(self, subreddit_name, sort=None):
        try:
            subreddit = self.reddit.get_subreddit(subreddit_name)
            hot = list(subreddit.get_hot(limit=DEFAULT_LIMIT))
            new = list(subreddit.get_new(limit=DEFAULT_LIMIT))
            result_dict = dict(map(lambda x: (x.fullname, x), hot), **dict(map(lambda x: (x.fullname, x), new)))

            log.info("Will search for dest posts candidates at %s posts in %s" % (len(result_dict), subreddit_name))
            result = result_dict.values()
            if sort:
                result.sort(cmp=sort)
            return result
        except Exception as e:
            return []

    def retrieve_comments(self, comments, parent_id, acc=None):
        if acc is None:
            acc = []
        for comment in comments:
            if isinstance(comment, MoreComments):
                try:
                    self.retrieve_comments(comment.comments(), parent_id, acc)
                except Exception as e:
                    log.debug("Exception in unwind more comments: %s" % e)
                    continue
            else:
                if comment.author and comment.parent_id == parent_id:
                    acc.append(comment)
        return acc


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class RedditReadBot(RedditBot):
    __metaclass__ = Singleton

    def __init__(self, db, user_agent=None):
        """
        :param user_agent: for reddit non auth and non oauth client
        :param lcp: low copies posts if persisted
        :param cp:  commented posts if persisted
        :return:
        """
        super(RedditReadBot, self).__init__(user_agent)
        self.db = db
        self.queues = {}
        log.info("Read bot inited!")

    def start_retrieve_comments(self, sub):
        if sub in self.queues:
            return self.queues[sub]

        self.queues[sub] = Queue()

        def f():
            while 1:
                start = time.time()
                log.info("Will start find comments for [%s]" % (sub))
                for el in self.find_comment(sub):
                    self.queues[sub].put(el)
                end = time.time()
                log.info("Was get all comments which found for [%s] at %s seconds... Will trying next."%(sub, end-start))
                time.sleep(DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT)

        Process(name="[%s] comment founder" % sub, target=f).start()
        return self.queues[sub]

    def find_comment(self, at_subreddit):
        def cmp_by_created_utc(x, y):
            result = x.created_utc - y.created_utc
            if result > 0.5:
                return 1
            elif result < 0.5:
                return -1
            else:
                return 0

        subreddit = at_subreddit
        all_posts = self.get_hot_and_new(subreddit, sort=cmp_by_created_utc)
        for post in all_posts:
            # log.info("Find comments in %s"%post.fullname)
            if self.db.is_post_used(post.fullname):
                # log.info("But post %s have low copies or commented yet"%post.fullname)
                continue
            try:
                copies = self._get_post_copies(post)
                copies = filter(lambda copy: _so_long(copy.created_utc, min_comment_create_time_difference) and \
                                             copy.num_comments > min_donor_num_comments,
                                copies)
                if len(copies) >= min_copy_count:
                    copies.sort(cmp=cmp_by_created_utc)
                    comment = None
                    for copy in copies:
                        # log.info("Validating copy %s for post %s"%(copy.fullname, post.fullname))
                        if copy.subreddit != post.subreddit and copy.fullname != post.fullname:
                            comment = self._retrieve_interested_comment(copy)
                            if comment and post.author != comment.author:
                                log.info("Find comment: [%s] \nin post [%s] at subreddit [%s]" % (
                                    comment, post.fullname, subreddit))
                                break
                                # else:
                                # log.info("But not valid comment found or authors are equals")
                                # else:
                                # log.info("But subreddits or fulnames are equals")
                    if comment:
                        yield {"post": post.fullname, "comment": comment.body}
                    else:
                        log.info("Can not find any valid comments for [%s]" % (post.fullname))
                else:
                    # log.info("But have low copies")
                    self.db.set_post_low_copies(post.fullname)
            except Exception as e:
                log.error(e)

    def _get_post_copies(self, post):
        search_request = "url:\'%s\'" % post.url
        copies = list(self.reddit.search(search_request))
        return list(copies)

    def _retrieve_interested_comment(self, copy):
        # prepare comments from donor to selection
        comments = self.retrieve_comments(copy.comments, copy.fullname)
        after = len(comments) / shift_copy_comments_part
        for i in range(after, len(comments)):
            comment = comments[i]
            if comment.ups >= min_donor_comment_ups and \
                            comment.ups <= max_donor_comment_ups and \
                    check_comment_text(comment.body):
                return comment

    def _get_all_post_comments(self, post, filter_func=lambda x: x):
        result = self.retrieve_comments(post.comments, post.fullname)
        result = set(map(lambda x: x.body, result))
        return result


class RedditWriteBot(RedditBot):
    def __init__(self, db, login):
        """
        :param subreddits: subbreddits which this bot will comment
        :param login_credentials:  dict object with this attributes: client_id, client_secret, redirect_url, access_token, refresh_token, login and password of user and user_agent 
         user agent can not present it will use some default user agent
        :return:
        """
        super(RedditWriteBot, self).__init__()
        self.lock = Lock()

        self.db = db

        state = db.get_bot_config(login)
        login_credentials = db.get_bot_access_credentials(login)

        self.subscribed_subreddits = set(state.get("ss")) or set()
        self.friends = set(state.get("frds")) or set()



        self.init_engine(login_credentials)
        self.init_work_cycle()

        self.used = set()
        self.configuration = BotConfiguration(state.get("live_config"))

        log.info("Write bot [%s] inited with credentials \n%s"
                 "\nConfiguration: \n%s"
                 "\nFriends: %s"
                 "\nSubscribed breddits:%s" % (login,
                                      "\n".join(["%s:\t%s" % (k, v) for k, v in login_credentials.get("info",{}).iteritems()]),
                                      "\n".join(["%s:\t%s" % (k, v) for k, v in self.configuration.data.iteritems()]),
                                      self.friends,
                                      self.subscribed_subreddits
                                      ))


    def init_engine(self, login_credentials):

        self.user_agent = login_credentials.get("user_agent", random.choice(USER_AGENTS))
        self.user_name = login_credentials["user"]

        r = praw.Reddit(self.user_agent)

        r.set_oauth_app_info(login_credentials['client_id'], login_credentials['client_secret'],
                             login_credentials['redirect_uri'])
        r.set_access_credentials(**login_credentials.get("info"))
        r.login(login_credentials["user"], login_credentials["pwd"], disable_warning=True)

        self.access_information = login_credentials.get("info")
        self.login_credentials = {"user": self.user_name, "pwd": login_credentials["pwd"]}
        self.reddit = r
        self.refresh_token()

    def refresh_token(self):
        self.access_information = self.reddit.refresh_access_information(self.access_information['refresh_token'])
        self.db.update_bot_access_credentials_info(self.user_name, self.access_information)
        self.reddit.login(self.login_credentials["user"], self.login_credentials["pwd"], disable_warning=True)

    def incr_counter(self, name):
        self.counters[name] += 1

    @property
    def action_function_params(self):
        return self.__action_function_params

    @action_function_params.setter
    def action_function_params(self, val):
        self.__action_function_params = val
        self.counters = {A_CONSUME: 0, A_VOTE: 0, A_COMMENT: 0, A_POST: 0}

    def init_work_cycle(self):
        consuming = random.randint(min_consuming, max_consuming)
        production = 100 - consuming

        prod_voting = random.randint(min_voting, max_voting)
        prod_commenting = 100 - prod_voting

        production_voting = (prod_voting * production) / 100
        production_commenting = (prod_commenting * production) / 100

        self.action_function_params = {A_CONSUME: consuming,
                                       A_VOTE: production_voting,
                                       A_COMMENT: production_commenting}
        log.info("MY [%s] WORK CYCLE: %s" % (self.user_name, self.action_function_params))

    def can_do(self, action):
        """
        Action
        :param action: can be: [vote, comment, consume]
        :return:  true or false
        """
        summ = sum(self.counters.values())
        action_count = self.counters[action]
        granted_perc = self.action_function_params.get(action)
        current_perc = int((float(action_count) / (summ if summ else 100)) * 100)

        return current_perc <= granted_perc

    def must_do(self, action):
        # result = reduce(lambda r, a: r and not self.can_do(a),
        #                 [a for a in self.action_function_params.keys() if a != action],
        #                 True)
        result = True
        for another_action in self.action_function_params.keys():
            if another_action == action:
                continue
            result = result and not self.can_do(another_action)
        return result

    def _is_want_to(self, coefficient):
        return coefficient >= 0 and random.randint(0, 10) >= coefficient

    def register_step(self, step_type, info=None):
        if step_type in self.counters:
            self.incr_counter(step_type)

        self.db.save_log_bot_row(self.user_name, step_type, info or {})
        self.persist_state()

        if info and info.get("fullname"):
            self.used.add(info.get("fullname"))

    @property
    def state(self):
        return {"ss": list(self.subscribed_subreddits),
                "frds": list(self.friends)}

    def persist_state(self):
        self.db.update_bot_internal_state(self.user_name, state=self.state)

    def do_see_post(self, post):
        """
        1) go to his url with yours useragent, wait random
        2) random check comments and random check more comments
        3) random go to link in comments
        #todo refactor action want to normal function
        :param post:
        :return:
        """
        try:
            res = requests.get(post.url, headers={"User-Agent": self.user_agent})
            log.info("%s was consume post: %s" % (self.user_name, res.url))
            self.register_step(A_CONSUME,
                               info={"url": post.url, "permalink": post.permalink, "fullname": post.fullname})
        except Exception as e:
            log.warning("Can not see post %s url %s \n EXCEPT [%s] \n %s" % (
                post.fullname, post.url, e, traceback.format_exc()))

        wt = self.wait(self.configuration.max_wait_time)

        if self._is_want_to(self.configuration.post_vote) and self.can_do("vote"):
            post_vote_count = random.choice([1, -1])
            try:
                post.vote(post_vote_count)
            except Exception as e:
                log.error(e)
            self.register_step(A_VOTE, info={"fullname": post.fullname, "vote": post_vote_count})
            self.wait(self.configuration.max_wait_time / 2)

        if self._is_want_to(self.configuration.comments) and wt > self.configuration.comment_mwt:  # go to post comments
            for comment in post.comments:
                if self._is_want_to(self.configuration.comment_vote) and self.can_do("vote"):  # voting comment
                    vote_count = random.choice([1, -1])
                    try:
                        comment.vote(vote_count)
                    except Exception as e:
                        log.error(e)
                    self.register_step(A_VOTE, info={"fullname": comment.fullname, "vote": vote_count})
                    self.wait(self.configuration.max_wait_time / 10)
                    if self._is_want_to(
                            self.configuration.comment_friend) and vote_count > 0 and comment.author.name not in self.friends:  # friend comment author
                        c_author = comment.author
                        if c_author.name not in self.friends:
                            try:
                                c_author.friend()
                            except Exception as e:
                                log.error(e)
                            self.friends.add(c_author.name)
                            self.register_step(A_FRIEND, info={"friend": c_author.name, "from": "comment"})
                            log.info("%s was add friend from comment %s because want coefficient is: %s",(self.user_name, comment.fullname, self.configuration.comment_friend))
                            self.wait(self.configuration.max_wait_time / 10)

                if self._is_want_to(self.configuration.comment_url):  # go to url in comment
                    if isinstance(comment, MoreComments):
                        comments = self.retrieve_comments(comment.comments(), comment.fullname, [])
                        if comments:
                            comment = random.choice(comments)
                        else:
                            continue
                    urls = re_url.findall(comment.body)
                    for url in urls:
                        try:
                            res = requests.get(url, headers={"User-Agent": self.user_agent})
                            log.info("%s was consume comment url: %s" % (self.user_name, res.url))
                        except Exception as e:
                            pass
                    if urls:
                        self.register_step(A_CONSUME, info={"urls": urls})

            self.wait(self.configuration.max_wait_time / 5)

        if self._is_want_to(
                self.configuration.subscribe) and post.subreddit.display_name not in self.subscribed_subreddits:  # subscribe sbrdt
            try:
                self.reddit.subscribe(post.subreddit.display_name)
            except Exception as e:
                log.error(e)
            self.subscribed_subreddits.add(post.subreddit.display_name)
            self.register_step(A_SUBSCRIBE, info={"sub": post.subreddit.display_name})
            self.wait(self.configuration.max_wait_time / 5)

        if self._is_want_to(
                self.configuration.author_friend) and post.author.name not in self.friends:  # friend post author
            try:
                post.author.friend()
            except Exception as e:
                log.error(e)
                log.error(self.reddit)

            self.friends.add(post.author.name)
            self.register_step(A_FRIEND, info={"fullname": post.author.name, "from": "post"})
            log.info("%s was add friend from post %s because want coefficient is: %s",(self.user_name, post.fullname, self.configuration.author_friend))
            self.wait(self.configuration.max_wait_time / 5)

    def set_configuration(self, configuration):
        self.configuration = configuration
        log.info("For %s configuration is setted: %s" % (self.user_name, configuration.data))

    def wait(self, max_wait_time):
        if max_wait_time > 1:
            wt = random.randint(1, max_wait_time)
            time.sleep(wt)
            return wt
        return max_wait_time

    def _get_random_near(self, slice, index, max):
        rnd = lambda x: random.randint(x / 10, x / 2) or 1
        max_ = lambda x: x if x < max and max_ != -1  else max
        count_random_left = max_(rnd(len(slice[0:index])))
        count_random_right = max_(rnd(len(slice[index:])))

        return [random.choice(slice[0:index]) for _ in xrange(count_random_left)], \
               [random.choice(slice[index:]) for _ in xrange(count_random_right)]

    def do_comment_post(self, post_fullname, subreddit_name, comment_text):
        log.info("[%s] will comment post [%s] (%s) by this text:\n%s" % (
            self.user_name, post_fullname, subreddit_name, comment_text))

        near_posts = self.get_hot_and_new(subreddit_name)
        for i, _post in enumerate(near_posts):
            if _post.fullname == post_fullname:
                see_left, see_right = self._get_random_near(near_posts, i, self.configuration.max_post_near_commented)
                try:
                    for p_ind in see_left:
                        self.do_see_post(p_ind)
                except Exception as e:
                    log.error(e)

                try:
                    for comment in filter(lambda comment: isinstance(comment, MoreComments), _post.comments):
                        comment.comments()
                        if random.randint(0, 10) > 6:
                            break
                except Exception as e:
                    log.error(e)

                try:
                    _post.add_comment(comment_text)
                    self.db.set_post_commented(_post.fullname)
                except Exception as e:
                    log.error(e)

                try:
                    for p_ind in see_right:
                        self.do_see_post(p_ind)
                except Exception as e:
                    log.error(e)

        try:
            if self._is_want_to(
                    self.configuration.subscribe_subreddit) and subreddit_name not in self.subscribed_subreddits:
                self.reddit.subscribe(subreddit_name)
                self.register_step(A_SUBSCRIBE, info={"sub": subreddit_name})
        except Exception as e:
            log.error(e)

        self.register_step(A_COMMENT, info={"fullname": post_fullname, "text": comment_text, "sub": subreddit_name})

    def live_random(self, max_iters=2000, max_actions=100, posts_limit=500, **kwargs):
        sub_posts = {}
        counter = 0
        for x in xrange(max_iters):
            random_sub = random.choice(self.db.get_bot_subs(self.user_name))
            if random_sub not in sub_posts:
                sbrdt = self.reddit.get_subreddit(random_sub)
                hot_posts = list(sbrdt.get_hot(limit=posts_limit))
                sub_posts[random_sub] = hot_posts
            else:
                hot_posts = sub_posts[random_sub]

            post = random.choice(hot_posts)
            if post.fullname not in self.used and self._is_want_to(7):
                self.do_see_post(post)
                counter += 1
            if random.randint(0, max_actions) < counter:
                break


class BotKapellmeister(Process):
    def __init__(self, name, db, read_bot):
        super(BotKapellmeister, self).__init__()
        self.db = db
        self.bot_name = name
        self.name = name

        self.w_bot = RedditWriteBot(db, login=name)
        self.r_bot = read_bot
        self.state = S_UNKNOWN

        self.lock = Lock()
        log.info("Bot kapellmeister inited.")

    def set_config(self, data):
        with self.lock:
            bot_config = BotConfiguration(data)
            self.w_bot.set_configuration(bot_config)

    def bot_check(self):
        ok = check_any_login(self.bot_name)
        if not ok:
            self.db.set_bot_live_state(self.bot_name, S_BAN, self.pid)
        return ok

    def get_bot_state(self):
        return self.db.get_bot_live_state(self.bot_name, self.pid)

    def run(self):
        while 1:
            try:
                if not self.bot_check():
                    break

                self.db.set_bot_live_state(self.bot_name, S_WORK, self.pid)
                for sub in self.db.get_bot_subs(self.bot_name):
                    queue = self.r_bot.start_retrieve_comments(sub)
                    try:
                        to_comment_info = queue.get(timeout=60)
                        self.w_bot.do_comment_post(to_comment_info.get("post"), sub, to_comment_info.get("comment"))
                    except Exception as e:
                        log.info("can not find any comments at %s" % sub)
                    self.w_bot.live_random(posts_limit=150)

                sleep_time = random.randint(1, 50)
                log.info("Bot [%s] will sleep %s seconds" % (self.bot_name, sleep_time))

                self.db.set_bot_live_state(self.bot_name, S_SLEEP, self.pid)
                time.sleep(sleep_time)
                self.w_bot.refresh_token()
            except Exception as e:
                log.exception(e)


class BotOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__bots = {}
        self.read_bot = RedditReadBot(DBHandler())
        self.lock = Lock()

    @property
    def bots(self):
        with self.lock:
            return self.__bots

    def add_bot(self, bot_name):
        with self.lock:
            if bot_name not in self.__bots:
                bot = BotKapellmeister(bot_name, DBHandler(), self.read_bot)
                self.__bots[bot_name] = bot
                bot.start()

    def get_bot_state(self, bot_name):
        with self.lock:
            result = S_UNKNOWN
            if bot_name in self.__bots:
                result = self.__bots[bot_name].get_bot_state()
            return result

    def stop_bot(self, bot_name):
        with self.lock:
            bot = self.__bots.get(bot_name)
            if bot:
                bot.terminate()
                bot.join(1)
                del self.__bots[bot_name]

    def toggle_bot_config(self, bot_name):
        with self.lock:
            if bot_name in self.__bots:
                def f():
                    db = DBHandler()
                    bot_config = db.get_bot_live_configuration(bot_name)
                    self.__bots[bot_name].set_config(bot_config)

                Process(name="config updater", target=f).start()


if __name__ == '__main__':
    pass
