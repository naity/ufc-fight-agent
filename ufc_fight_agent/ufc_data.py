import requests
from typing import Optional
from bs4 import BeautifulSoup
from dataclasses import dataclass, field


@dataclass
class Event:
    name: str
    date: str
    location: str
    event_url: str
    fights: list = field(default_factory=list)


@dataclass
class FighterStats:
    stats: dict[str, str] = field(default_factory=dict)
    recent_fights: list[str] = field(default_factory=list)


@dataclass
class Fight:
    fight_url: str
    fighter_1: str
    fighter_2: str
    weight_class: str
    title_fight: bool
    fighter_1_stats: FighterStats = field(default_factory=FighterStats)
    fighter_2_stats: FighterStats = field(default_factory=FighterStats)


def get_page_response(url: str):
    """
    Gets the response from a URL with proper headers and error handling.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        # print(f"Failed to retrieve page {url}: {e}")
        return None


def extract_events(max_events: Optional[int] = None):
    """
    Extracts UFC event information from the upcoming events page.
    """

    url = "http://ufcstats.com/statistics/events/upcoming"
    events = []

    response = get_page_response(url)
    if not response:
        return events

    soup = BeautifulSoup(response.text, "html.parser")
    for row in soup.select("tr.b-statistics__table-row"):
        event_name = row.select_one("a.b-link")
        event_date = row.select_one("span.b-statistics__date")
        event_location = row.select_one(
            "td.b-statistics__table-col.b-statistics__table-col_style_big-top-padding"
        )

        if event_name and event_date and event_location:
            events.append(
                Event(
                    name=event_name.get_text(strip=True),
                    date=event_date.get_text(strip=True),
                    location=event_location.get_text(strip=True),
                    event_url=event_name["href"],
                )
            )

        if max_events and len(events) >= max_events:
            break

    return events


def extract_fights(event_url: str):
    """
    Extracts fight information from a specific event page.
    """

    fights = []

    response = get_page_response(event_url)
    if not response:
        return fights

    soup = BeautifulSoup(response.text, "html.parser")

    for fight_row in soup.select("tbody > tr.b-fight-details__table-row"):
        fight_link = fight_row.get("data-link")

        fighter_names = [
            a.get_text(strip=True)
            for a in fight_row.select(
                "td.b-fight-details__table-col a.b-link.b-link_style_black[href]"
            )
        ]

        weight_class_cell = fight_row.select("td.b-fight-details__table-col")[6]
        weight_class = (
            weight_class_cell.get_text(strip=True).split("\n")[0]
            if weight_class_cell
            else None
        )

        title_fight = bool(fight_row.select_one("img[src*='belt.png']"))

        if fight_link and len(fighter_names) == 2 and weight_class is not None:
            fights.append(
                Fight(
                    fight_url=fight_link.strip(),
                    fighter_1=fighter_names[0],
                    fighter_2=fighter_names[1],
                    weight_class=weight_class,
                    title_fight=title_fight,
                )
            )

    return fights


def extract_matchup(fight_url: str):
    """
    Extracts matchup data from a fight page.
    """
    fighter_1_stats = FighterStats()
    fighter_2_stats = FighterStats()

    response = get_page_response(fight_url)
    if not response:
        return (fighter_1_stats, fighter_2_stats)

    soup = BeautifulSoup(response.text, "html.parser")

    current_section = None

    for row in soup.select("tr"):
        # Check if it's a section header
        header = row.select_one("th.b-fight-details__table-col")
        if header:
            current_section = header.get_text(strip=True)
            continue

        # Extract data row
        cols = row.select("td.b-fight-details__table-col")
        if len(cols) != 3:
            continue  # Skip invalid rows

        label = cols[0].get_text(strip=True)
        value_1 = cols[1].get_text(strip=True)
        value_2 = cols[2].get_text(strip=True)

        if current_section == "Most recent fights (Newest First)":
            if value_1:
                fighter_1_stats.recent_fights.append(value_1)
            if value_2:
                fighter_2_stats.recent_fights.append(value_2)
        else:
            fighter_1_stats.stats[label] = value_1
            fighter_2_stats.stats[label] = value_2

    return (fighter_1_stats, fighter_2_stats)
