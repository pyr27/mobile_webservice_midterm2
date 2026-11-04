"""온디바이스 얼굴 식별 기반 공부 세션 자동 측정 (편의 기능 ①).

- YOLO가 잡은 person 영역에서 얼굴을 찾고, enroll_face.py 로 학습한 LBPH 모델로 '본인' 여부를 판정한다.
- 본인이 보이면 세션 시작, ABSENT_SEC 이상 안 보이면 세션 종료 후 서버의 /api_root/StudySession/ 로 전송한다.
- 얼굴 식별은 모두 Edge(PC)에서 수행되며, 서버로는 시작/종료 시각만 보낸다 (영상·얼굴 데이터 미전송).
"""
import os
import time
from datetime import datetime

import cv2
import requests

# 얼굴 검출용 Haar cascade: 레포에 동봉한 파일 우선, 없으면 OpenCV 내장 경로
CASCADE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'haarcascade_frontalface_default.xml')
if not os.path.exists(CASCADE):
    CASCADE = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'


def create_lbph():
    """OpenCV 4.x / 5.x 양쪽 API 지원."""
    face = cv2.face
    if hasattr(face, 'LBPHFaceRecognizer_create'):
        return face.LBPHFaceRecognizer_create()
    return face.LBPHFaceRecognizer.create()


class StudySession:
    HOST = os.environ.get('BLOG_HOST', 'http://127.0.0.1:8000')
    username = os.environ.get('BLOG_USER', 'admin')
    password = os.environ.get('BLOG_PASS', 'password')
    ABSENT_SEC = float(os.environ.get('STUDY_ABSENT_SEC', 30))   # 이 시간 이상 안 보이면 세션 종료
    MIN_SESSION_SEC = float(os.environ.get('STUDY_MIN_SEC', 60))  # 이보다 짧은 세션은 버림
    THRESHOLD = float(os.environ.get('FACE_THRESHOLD', 70))       # LBPH 거리: 작을수록 유사 (보통 50~80)

    def __init__(self, token=None):
        self.enabled = False
        model = os.path.join('faces', f'{self.username}.yml')
        if not (hasattr(cv2, 'face') and os.path.exists(model)):
            print(f'[StudySession] disabled: {model} 없음 (python enroll_face.py --name {self.username})')
            return
        self.recognizer = create_lbph()
        self.recognizer.read(model)
        self.detector = cv2.CascadeClassifier(CASCADE)
        self.token = token or self._login()
        self.started_at = None      # 현재 세션 시작 시각
        self.last_seen = 0.0        # 본인이 마지막으로 보인 시각
        self.enabled = True
        print(f'[StudySession] enabled for {self.username}')

    def _login(self):
        res = requests.post(self.HOST + '/api-token-auth/', {'username': self.username, 'password': self.password})
        res.raise_for_status()
        return res.json()['token']

    # ------------------------------------------------------------------
    def is_owner(self, frame, det, names):
        """person 박스 안에서 얼굴을 찾아 본인인지 판정."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for *xyxy, conf, cls in det:
            if names[int(cls)] != 'person':
                continue
            x1, y1, x2, y2 = (int(v) for v in xyxy)
            roi = gray[max(0, y1):y2, max(0, x1):x2]
            if roi.size == 0:
                continue
            for (fx, fy, fw, fh) in self.detector.detectMultiScale(roi, 1.2, 5, minSize=(60, 60)):
                face = cv2.resize(roi[fy:fy + fh, fx:fx + fw], (200, 200))
                label, dist = self.recognizer.predict(face)
                owner = label == 0 and dist < self.THRESHOLD
                color = (0, 255, 0) if owner else (0, 0, 255)
                cv2.rectangle(frame, (x1 + fx, y1 + fy), (x1 + fx + fw, y1 + fy + fh), color, 2)
                cv2.putText(frame, f'{"ME" if owner else "?"} {dist:.0f}', (x1 + fx, y1 + fy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                if owner:
                    return True
        return False

    def update(self, frame, det, names):
        """매 프레임 호출. 세션 상태를 갱신하고 화면에 오버레이를 그린다."""
        if not self.enabled:
            return
        now = time.time()
        if self.is_owner(frame, det, names):
            self.last_seen = now
            if self.started_at is None:
                self.started_at = datetime.now()
                print(f'[StudySession] start {self.started_at:%H:%M:%S}')
        elif self.started_at is not None and now - self.last_seen > self.ABSENT_SEC:
            self.finish()

        if self.started_at is not None:
            elapsed = int(now - self.started_at.timestamp())
            away = int(now - self.last_seen)
            text = f'STUDYING {elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}'
            if away > 2:
                text += f'  (away {away}s)'
            cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        else:
            cv2.putText(frame, 'IDLE', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    def finish(self):
        """세션 종료 → 서버 전송. 종료 시각은 마지막으로 보인 시각."""
        ended_at = datetime.fromtimestamp(self.last_seen)
        duration = int((ended_at - self.started_at).total_seconds())
        started, self.started_at = self.started_at, None
        if duration < self.MIN_SESSION_SEC:
            print(f'[StudySession] discard short session ({duration}s)')
            return
        res = requests.post(self.HOST + '/api_root/StudySession/',
                            headers={'Authorization': 'Token ' + self.token, 'Accept': 'application/json'},
                            data={'started_at': started.isoformat(), 'ended_at': ended_at.isoformat(),
                                  'duration_sec': duration})
        print(f'[StudySession] end {ended_at:%H:%M:%S} duration={duration}s -> {res.status_code} {res.text[:120]}')
