from sqlalchemy import create_engine, Column, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, nullable=False)
    is_profile_open = Column(Integer, nullable=False)
    comments_count = Column(Integer, nullable=False)
    search_date = Column(Integer, nullable=False)
    mood_id = Column(Integer, ForeignKey('moods.mood_id'), nullable=False)

    mood = relationship("Mood", back_populates="users")
    sent_comments = relationship("Comment", foreign_keys="Comment.sender_id", back_populates="sender")


class Mood(Base):
    __tablename__ = "moods"
    mood_id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(50), nullable=False)

    users = relationship("User", back_populates="mood")
    comments = relationship("Comment", back_populates="mood")


class Comment(Base):
    __tablename__ = "comments"
    comment_id = Column(Integer, primary_key=True, nullable=False)
    text = Column(String(280), nullable=False)
    sender_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    receiver_id = Column(Integer, nullable=False)
    type = Column(Integer, nullable=False)
    type_id = Column(Integer, nullable=False)
    mood_id = Column(Integer, ForeignKey('moods.mood_id'), nullable=False)
    creation_date = Column(Integer, nullable=False)

    mood = relationship("Mood", back_populates="comments")
    sender = relationship("User", foreign_keys="Comment.sender_id", back_populates="sent_comments")


engine = create_engine("sqlite:///database/comments.db?echo=True")

Base.metadata.create_all(engine)

factory = sessionmaker(bind=engine)
session = factory()
