queryAnimeLists = '''
	query ($username: String){
		MediaListCollection (userName: $username, type: ANIME) {
			lists {
				status
				entries {
					media {
						meanScore
					}
					score(format: POINT_100)
					mediaId
				}
			}
		}
	}
	'''

queryRecsForAnime = '''
	query ($id: Int) {
		Media (id: $id) {
			id
			title {
				english
				romaji
			}
			recommendations(sort: RATING_DESC, page: 1, perPage: 10){
				pageInfo{
					perPage
					hasNextPage
				}
				nodes {
					mediaRecommendation {
						id
						title {
							english
							romaji
						}
						meanScore
					}
				}
			}
		}
	}
	'''
