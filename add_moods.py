from database import factory, Mood

session = factory()

moods = [
    Mood(mood_id=0, name="neutral"),
    Mood(mood_id=1, name="positive"),
    Mood(mood_id=2, name="negative")
]

session.add_all(moods)
session.commit()
session.close()
