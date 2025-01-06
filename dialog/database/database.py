from sqlalchemy import Column, Integer, String, Float, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class DownloadRecord(Base):
    tablename = "downloads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String, nullable=True)
    media_type = Column(String, nullable=False)  # "video" или "audio"
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    filesize = Column(Float, nullable=True)  # Размер файла в байтах
    timestamp = Column(String, nullable=False)  # Время загрузки

# Настраиваем движок и создаём таблицу
engine = create_engine("sqlite:///downloads.db")  # Или другой движок
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)





from datetime import datetime

def log_download(user_id, username, media_type, url, title, filesize):
    """Сохраняет информацию о загрузке в базу данных."""
    session = SessionLocal()
    try:
        download = DownloadRecord(
            user_id=user_id,
            username=username,
            media_type=media_type,
            url=url,
            title=title,
            filesize=filesize,
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        session.add(download)
        session.commit()
        print(f"Загрузка записана в БД: {user_id}, {title}")
    except Exception as e:
        print(f"Ошибка при записи в БД: {e}")
    finally:
        session.close()


def get_user_downloads(user_id):
    """Получает список загрузок пользователя из базы данных."""
    session = SessionLocal()
    try:
        downloads = session.query(DownloadRecord).filter_by(user_id=user_id).all()
        return [
            {
                "id": download.id,
                "username": download.username,
                "media_type": download.media_type,
                "url": download.url,
                "title": download.title,
                "filesize": download.filesize,
                "timestamp": download.timestamp,
            }
            for download in downloads
        ]
    except Exception as e:
        print(f"Ошибка при чтении данных из БД: {e}")
        return []
    finally:
        session.close()


log_download(
    user_id=12345,
    username="test_user",
    media_type="video",
    url="https://youtu.be/test",
    title="Test Video",
    filesize=5000000
)