import time

from app.services.jobs import dequeue
from app.services.pipeline import process_media


def main() -> None:
    print("Transcribe Hub worker listening on queue transcribe-jobs")
    while True:
        try:
            job = dequeue(timeout=5)
            if not job:
                continue
            process_media(job["media_file_id"])
        except Exception as exc:
            print("worker error:", exc)
            time.sleep(2)


if __name__ == "__main__":
    main()
