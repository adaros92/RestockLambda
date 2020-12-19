import boto3
import os
import tweepy


def _get_aws_client(service: str, client: boto3.client = None) -> boto3.client:
    """Retrieves a boto3 client for the given service name if one is not already provided"""
    if not client:
        client = boto3.client(service)
    return client


def _get_sns_client(client: boto3.client = None) -> boto3.client:
    """Retrieves an SNS boto3 client"""
    return _get_aws_client("sns", client)


def _send_message(message: str, subject: str, topic_arn: str, client: boto3.client) -> dict:
    """Sends a given message to an SNS topic ARN with the provided SNS client

    :returns the response received back from the request
    """
    response = client.publish(
        TopicArn=topic_arn,
        Message=message,
        Subject=subject
    )
    return response


def _verify_event_payload(event: dict) -> None:
    """Raises exception if the Lambda input is invalid

    :param event - a dictionary containing the key/value pairs passed in as an event payload to the Lambda
    """
    required_inputs = [
        "subject", "consumer_key", "consumer_secret", "access_token",
        "access_token_secret", "screen_name", "search_terms", "special_unicode"]
    for required_input in required_inputs:
        if required_input not in event:
            raise ValueError("The provided event payload is missing required input - {0}".format(required_input))
    assert type(event["search_terms"]) == list and type(event["special_unicode"]) == list


def _get_authorized_tweepy_client(
        consumer_key: str, consumer_secret: str, access_token: str, access_token_secret: str) -> tweepy.API:
    """Retrieves an authorized Tweepy API client to use when extracting Tweets

    :param consumer_key
    :param consumer_secret
    :param access_token
    :param access_token_secret
    :returns a signed Tweepy client
    """
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    return tweepy.API(auth)


def _get_matching_tweets(screen_name: str, search_terms: list, special_unicode: list, client: tweepy.API) -> list:
    """Retrieves the last 20 Tweets in the given user's timeline and filters them to those containing the given terms
    and unicode characters

    :param screen_name - the Twitter user handle to search for
    :param search_terms - a list of terms to filter Tweets by (must contain all terms in the list)
    :param special_unicode - a list of unicode values (equivalent of ord(char)) for any special characters (emojis)
    :param client - the Tweepy client to use for the request to retrieve Tweets
    :returns a list of matching Tweets containing the required terms and special characters
    """
    # Get the last 20 tweets in the user's timeline
    user_tweets = client.user_timeline(screen_name=screen_name)
    matching_tweets = []
    # Find matching tweets in the user's timeline
    for tweet in user_tweets:
        tweet_text = tweet.text
        # Retrieve individual unicode characters in the tweet text to check for any special characters
        unicode_chars_in_tweet = set([ord(character) for character in tweet_text])
        matching = True
        # If any of the search terms are not in the tweet, skip it
        for search_term in search_terms:
            if search_term.lower() not in tweet_text.lower():
                matching = False
                break
        # If any of the special unicode characters are missing from the tweet, also skip it
        for special_unicode_char in special_unicode:
            if special_unicode_char not in unicode_chars_in_tweet:
                matching = False
                break
        # If all of the required search terms and special unicode characters are in the tweet, keep track of it
        if matching:
            matching_tweets.append(tweet_text)
    return matching_tweets


def lambda_handler(event: dict, _) -> dict:
    """ The main handler function that will run as a Lambda

    :param event - a dictionary of key/value data to operate with
    :returns a response from the SNS service when the Lambda sends out a notification, otherwise an empty dictionary
    """
    # Get event input provided to Lambda and verify it (exception will be thrown at this point if anything is off)
    _verify_event_payload(event)
    # Retrieve matching tweets for the given user
    tweepy_client = _get_authorized_tweepy_client(
        event["consumer_key"], event["consumer_secret"],
        event["access_token"], event["access_token_secret"]
    )
    matching_tweets = _get_matching_tweets(
        event["screen_name"], event["search_terms"],
        event["special_unicode"], tweepy_client
    )
    message = "\n\n".join(matching_tweets)
    response = {}
    # Send a message if there are any matching tweets
    if len(matching_tweets) > 0:
        # Get the SNS topic ARN to send an alert message to from Lambda's environment variables
        sns_topic_arn = os.environ["sns_topic_arn"]
        # Retrieve the SNS client
        sns_client = _get_sns_client()
        # Send the message
        response = _send_message(message, event["subject"], sns_topic_arn, sns_client)
    return response
