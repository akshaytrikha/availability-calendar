# External
import datetime
from typing import List, Dict
from tqdm.auto import tqdm
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

# Internal
from config import AVAILABILITY_CALENDAR_ID

# If modifying these SCOPES, delete the token.pickle file.
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def authenticate_google() -> Credentials:
    """Authenticate and return calendar service object"""
    # Load client-side credentials
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    #  Opens the browser-based UI for authentication token
    creds = flow.run_local_server(port=0)

    return creds


def get_all_events(
    service: Resource, calendar_id="primary", time_min=None, time_max=None
) -> List[Dict]:
    """Fetch all events from primary calendar within specified time range.

    Args:
        service: The calendar service object.
        calendar_id: The calendar ID to fetch events from.
        time_min: The minimum time to fetch events from.
        time_max: The maximum time to fetch events until.
    Returns:
        List[Dict] of events within the specified time range.

        schema e.g.
        {
            'kind': 'calendar#event',
            'etag': '"etag"',
            'id': 'id',
            'status': 'confirmed',
            'htmlLink': 'https://www.google.com/calendar/event?eid=id',
            'created': '2024-09-12T17:48:23.000Z',
            'updated': '2024-09-12T19:40:41.143Z',
            'summary': 'Scaling Research Group Meeting',
            'location': 'Hearst Memorial Mining Building, Berkeley, CA 94720, USA ',
            'colorId': '2',
            'creator': {
                'email': 'me@berkeley.edu',
                'self': True
            },
            'organizer': {
                'email': 'me@berkeley.edu',
                'self': True
            },
            'start': {
                'dateTime': '2024-09-17T16:00:00-07:00',
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': '2024-09-17T17:00:00-07:00',
                'timeZone': 'America/Los_Angeles'
            },
            'iCalUID': 'id@google.com',
            'sequence': 0,
            'attendees': [
                {
                    'email': 'person@berkeley.edu',
                    'responseStatus': 'accepted'
                },
                {
                    'email': 'me@berkeley.edu',
                    'organizer': True,
                    'self': True,
                    'responseStatus': 'accepted'
                }
            ],
            'reminders': {
                'useDefault': True
            },
            'eventType': 'default'
        }
    """

    # Fetch events from the specified calendar
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return events_result.get("items", [])


def delete_overlapping_events(
    service: Resource, calendar_id: str, start: str, end: str
):
    """Delete events in the Availability calendar that overlap with the given time range."""
    # Fetch existing events in the Availability calendar within the time range
    availability_events = get_all_events(
        service, calendar_id=calendar_id, time_min=start, time_max=end
    )

    for event in availability_events:
        event_start = event["start"].get("dateTime", event["start"].get("date"))
        event_end = event["end"].get("dateTime", event["end"].get("date"))

        # If the event overlaps with the new busy period, delete it
        if event_start <= end and event_end >= start:
            service.events().delete(
                calendarId=calendar_id, eventId=event["id"]
            ).execute()


def create_busy_event(service: Resource, start: str, end: str):
    """Create a busy event in Availability given calendar.

    Args:
        service: Calendar service object.
        calendar_id: Calendar ID to create the event in.
        start: Event start time.
        end: Event end time.
    """
    # Create a new busy event
    event = {
        "summary": "Busy",
        "start": {
            "dateTime": start,
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end,
            "timeZone": "UTC",
        },
    }
    service.events().insert(calendarId=AVAILABILITY_CALENDAR_ID, body=event).execute()


def delete_all_availability_events(service: Resource, time_min: str, time_max: str):
    """Delete all events in the Availability calendar.

    Args:
        service: Calendar service object.
        time_min: Minimum time to fetch events from.
        time_max: Maximum time to fetch events from.
    """
    # Fetch all events from the Availability calendar
    availability_events = get_all_events(
        service,
        calendar_id=AVAILABILITY_CALENDAR_ID,
        time_min=time_min,
        time_max=time_max,
    )

    # Loop through the events and delete each one
    for event in tqdm(
        availability_events, desc="Deleting Availability Calendar Events"
    ):
        event_id = event["id"]
        service.events().delete(
            calendarId=AVAILABILITY_CALENDAR_ID, eventId=event_id
        ).execute()


def sync_availability(service: Resource, time_min: str, time_max: str):
    """Sync primary calendar events to the Availability calendar.

    Args:
        service: Calendar service object.
        time_min: Minimum time to fetch events from.
        time_max: Maximum time to fetch events from.
    """
    # Fetch primary calendar events
    primary_events = get_all_events(
        service, calendar_id="primary", time_min=time_min, time_max=time_max
    )

    # Loop through primary calendar events and copy them to the Availability calendar
    for event in tqdm(primary_events, desc="Creating Availability Calendar Events"):
        # Only sync events where the user is marked as busy
        if event.get("transparency", "") != "transparent":
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            # Create or update busy event in the Availability calendar
            create_busy_event(service, start, end)


if __name__ == "__main__":
    # Authenticate and build the calendar service
    creds: Credentials = authenticate_google()
    service: Resource = build("calendar", "v3", credentials=creds)

    # Define the time range for fetching events
    now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
    end_time = (
        datetime.datetime.utcnow() + datetime.timedelta(days=7)
    ).isoformat() + "Z"  # One week ahead

    delete_all_availability_events(service, now, end_time)
    sync_availability(service, now, end_time)
