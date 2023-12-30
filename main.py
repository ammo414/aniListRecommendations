import requests
import time

from graphqlqueries import queryAnimeLists, queryRecsForAnime

BASE_URL: str = 'https://anilist.co'
QUERY_URL: str = 'https://graphql.anilist.co'


class AnimeData:
    def __init__(self, name):
        self.name: str = name
        self.gettingRecsFor: list = []
        self.filterTheseOut: list = []
        self.reasonWhyRecommended: dict = {}
        self.numberOfTimesRecommended: dict = {}
        self.finalRecs: set = set()

    def getRecsFor(self, listOfAnime: list):
        self.gettingRecsFor.extend(listOfAnime)

    def filterRecsOut(self, listOfAnime: list):
        self.filterTheseOut.extend(listOfAnime)

    def recommendedBecause(self, rec: tuple, reason: str):
        if rec[0] not in self.reasonWhyRecommended:
            self.reasonWhyRecommended[rec[0]] = reason

    def addRecsToGive(self, rec: tuple):
        self.finalRecs.add(rec)

    def addCountOfTimesRecommended(self, rec: tuple):
        if rec in self.numberOfTimesRecommended:
            self.numberOfTimesRecommended[self] += 1
        else:
            self.numberOfTimesRecommended[self] = 1


def getUserName() -> str:
    """
    asks for username and ensures it is a valid aniList username
    :return:
    """
    username: str
    usernameURL: str

    username = input('anilist username? ')
    usernameURL = BASE_URL + '/user/' + username
    while requests.head(usernameURL).status_code != 200:  # should this be an api query instead?
        print('invalid username')
        username = input('anilist username? ')
        usernameURL = BASE_URL + '/user/' + username
    return username


def thresholdIsValid(threshold: str) -> bool:
    """
    given a threshold, ensures it is a number and is between 0 and 100
    :param threshold: input from user
    :return: true if valid, false otherwise
    """
    try:
        threshold = int(threshold)
    except ValueError:
        print('not a numeric value.')
        return False
    if threshold > 100:
        print('above 100')
        return False
    elif threshold < 0:
        print('below 0')
    else:
        return True


def getAndValidateThreshold() -> int:
    """
    asks for a threshold and ensures it is a number between 0 and 100
    :return: threshold
    """
    threshold: str

    threshold = input('threshold? ')
    while not thresholdIsValid(threshold):
        threshold = input('threshold? ')
    return int(threshold)


def rateLimitHit(JSONdict: dict) -> bool:
    """
    determines if we hit the rate limit
    :param JSONdict: dict deserialized from a json string
    :return: boolean of if we hit the rate limit
    """
    return JSONdict['data'] is None and JSONdict['errors'][0]['status'] == 429


def getAnimeLists(username: str) -> list:
    """
    for an aniList username, query for all their watchlists
    :param username: aniList username
    :return: list of watchlists
    """
    query: str
    response: requests.Response
    searchResults: dict
    animeLists: list

    query = queryAnimeLists
    response = requests.post(QUERY_URL, json={'query': query, 'variables': {'username': username}})
    searchResults = response.json()
    if rateLimitHit(searchResults):
        print('hit the rate limit, try again')
    animeLists = searchResults['data']['MediaListCollection']['lists']
    return animeLists


def processCompleted(lst: dict, scoreThreshold=65) -> list:
    """
    finds completed anime that we like (based on scoreThreshold)
    :param lst: animeList we are processing (should always be COMPLETED)
    :param scoreThreshold: anime which we rate at least this high will be considered. Default is 65/100
    :return: list of anime that we want recommendations for
    """
    return [entry['mediaId'] for entry in lst['entries'] if entry['score'] >= scoreThreshold]


def processOtherLists(lst: dict) -> list:
    """
    finds anime that shouldn't be recommended (already watched, plan on watching, etc.)
    :param lst: animeList that consists of anime that shouldn't be recommended
    :return: list of anime that we don't want recommended to us
    """
    return [entry['mediaId'] for entry in lst['entries']]


def getMediaPage(mediaId: int) -> dict:
    """
    gets media data, including recommendations
    :param mediaId: anime's ID
    :return: dict of media
    """

    query: str
    response: requests.Response
    mediaPage: dict

    time.sleep(1)  # rate limiting
    query = queryRecsForAnime
    response = requests.post(QUERY_URL, json={'query': query, 'variables': {'id': mediaId}})
    mediaPage = response.json()
    # if we hit the rate limit, wait 65 seconds and try again
    if rateLimitHit(mediaPage):
        print('hit the rate limit, waiting')
        time.sleep(5)
        for t in range(20):
            print('.', end='')
            time.sleep(3)
        getMediaPage(mediaId)
    return mediaPage


def processRecommendations(mediaPage: dict, recProfile: AnimeData, threshold=65) -> None:
    """
    unpacks recommendation dict and determines if the rec is worthwhile based on scoreThreshold
    :param mediaPage: dict of media and its recommendations
    :param recProfile: all relevant anime data for the user
    :param threshold: anime must be at least this score to be recommended. default is 65/100
    :return: set of recommendations
    """
    mediaName: str
    pageOfRecs: list  # subset of medaPage data. List of the recommendations data
    media: dict  # subset of pageOfRecs
    recId: int
    recScore: int
    recName: str

    mediaName = mediaPage['data']['Media']['title']['english'] \
                or mediaPage['data']['Media']['title']['romaji']  # returns first truthy result
    print(f'Getting Recs for {mediaName!r}')
    pageOfRecs = mediaPage['data']['Media']['recommendations']['nodes']
    for media in pageOfRecs:
        if media['mediaRecommendation'] is None:
            break
        recId = media['mediaRecommendation']['id']
        recScore = media['mediaRecommendation']['meanScore']
        recName = media['mediaRecommendation']['title']['english'] \
                  or media['mediaRecommendation']['title']['romaji']  # returns first truthy result
        recName = recName.replace(',', '')  # remove commas for the sake of saving to csv
        if recId in recProfile.filterTheseOut:
            print(f'\t{recName!r} is already in a watchlist: skipping')
            continue
        if recScore >= threshold:
            recProfile.addRecsToGive((recId, recScore, recName))
            print(f'\t{recName!r} has a score of {recScore}')
            if recId not in recProfile.reasonWhyRecommended:
                recProfile.recommendedBecause((recId, recScore, recName), f'has a score of {recScore}')
        recProfile.addCountOfTimesRecommended((recId, recScore, recName))


def mainFunction(username: str, recProfile: AnimeData, threshold: int) -> set:
    """

    :param username: aniList username
    :param recProfile: all relevant anime data for the user
    :param threshold: score that anime needs to be recommended
    :return:
    """
    mediaLists: list  # list of watchLists - PLANNING, - DROPPED, etc.)
    watchList: dict  # reflects structure in graphqlqueries.queryAnimeLists
    mediaId: int
    mediaPage: dict  # reflects structure in graphqlqueries.queryRecsForAnime
    rec: tuple  # (recId, recScore, recName)
    timesRecommended: int

    if requests.head(BASE_URL).status_code == 200:
        mediaLists = getAnimeLists(username)
        for watchList in mediaLists:
            if watchList['status'] == 'COMPLETED' \
                    or watchList['status'] == 'CURRENT':
                recProfile.getRecsFor(processCompleted(watchList, threshold))
            recProfile.filterRecsOut(processOtherLists(watchList))

        # now that we have our list of anime that we want to get recs for, get the recs
        for mediaId in recProfile.gettingRecsFor:
            mediaPage = getMediaPage(mediaId)
            processRecommendations(mediaPage, recProfile, threshold)
        for rec, timesRecommended in recProfile.numberOfTimesRecommended.items():
            if timesRecommended > 4:
                if rec not in recProfile.finalRecs:
                    print(f'\t{rec[2]!r} was recommended {timesRecommended} times')
                    if rec[0] not in recProfile.reasonWhyRecommended:
                        recProfile.recommendedBecause(rec[0], f'has been recommended {timesRecommended} times.')
                    recProfile.addRecsToGive(rec)
    else:
        print('anilist is down, please try again later.')
        return {'error: anilist is down, please try again later.'}


def saveRecsToCSV(recProfile, filename: str) -> None:
    """
    takes in recommendations and prints to file
    :rtype: None
    :param filename: name of file to save data to. will override current content
    :param recProfile: all relevant anime data for the user
    """
    rec: tuple
    recId: int
    line: str

    with open(filename + '.csv', 'w') as file:
        file.write(','.join(['animeId', 'animeScore', 'animeTitle', 'reasonRecommended', '\n']))
        for rec in recProfile.finalRecs:  # intentionally made this probabilistic
            recId = rec[0]
            line = str(rec).removeprefix('(').removesuffix(')')
            line = ','.join([line, recProfile.reasonWhyRecommended[recId]])
            file.write(line+'\n')


if __name__ == "__main__":
    USERNAME: str = getUserName()
    RECPROFILE: AnimeData = AnimeData(USERNAME)
    THRESHOLD: int = getAndValidateThreshold()
    mainFunction(USERNAME, RECPROFILE, THRESHOLD)
    saveRecsToCSV(RECPROFILE, 'recsOnFile')
    print(RECPROFILE.finalRecs)
