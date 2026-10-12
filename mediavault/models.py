import json
import os
import random
import time

class MediaItem:
    def __init__(self, title, image_path, score=50, description="", entry_type="Bilder", video_link="", watched_counter=0, last_watched=0.0, rating_count=0, group=""):
        self.title = title
        self.image_path = image_path
        self.score = score
        self.watched_counter = watched_counter
        self.description = description
        self.entry_type = entry_type
        self.video_link = video_link
        self.last_watched = last_watched
        self.rating_count = rating_count
        self.group = group

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, data):
        return cls(
            title=data.get("title", ""),
            image_path=data.get("image_path", ""),
            score=data.get("score", 50),
            description=data.get("description", ""),
            entry_type=data.get("entry_type", "Bilder"),
            video_link=data.get("video_link", ""),
            watched_counter=data.get("watched_counter", 0),
            last_watched=data.get("last_watched", 0.0),
            rating_count=data.get("rating_count", 0),
            group=data.get("group", "")
        )

class MediaDatabase:
    def __init__(self, filepath="media_data.json"):
        self.filepath = filepath
        self.entries = []

    def load(self):
        if not os.path.exists(self.filepath): return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.entries = [MediaItem.from_dict(item) for item in data]
        except json.JSONDecodeError:
            pass

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=4)

    def add(self, entry):
        self.entries.append(entry)
        self.save()

    def delete_multiple(self, entries_to_delete):
        self.entries = [e for e in self.entries if e not in entries_to_delete]
        self.save()

    def get_by_type(self, entry_type):
        return [e for e in self.entries if e.entry_type == entry_type]

    def get_all_groups(self):
        groups = {e.group for e in self.entries if getattr(e, 'group', "").strip()}
        return sorted(list(groups))

    def get_random(self, pool, smart=False, recent_picks=None):
        if not pool: return None
        recent_picks = recent_picks or []
        filtered = [e for e in pool if e not in recent_picks]
        if not filtered and pool: filtered = pool

        if not smart:
            return random.choice(filtered)

        current_time = time.time()
        weights = []
        for e in filtered:
            w = e.score + 20 
            w *= (0.85 ** e.watched_counter)
            if e.last_watched > 0:
                days_since = (current_time - e.last_watched) / 86400 
                if days_since < 1: w *= 0.3 
                elif days_since < 7: w *= 0.6 
            weights.append(max(1, w))
            
        return random.choices(filtered, weights=weights, k=1)[0]