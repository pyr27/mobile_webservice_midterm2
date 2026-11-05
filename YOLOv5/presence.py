"""온디바이스 얼굴 식별 기반 재석/자리 비움 감지 (편의 기능 ①).

- YOLO가 잡은 person 영역에서 얼굴을 찾고, enroll_face.py 로 학습한 LBPH 모델로 '등록 사용자' 여부를 판정한다.
- 등록 사용자가 보이면 '재석', ABSENT_SEC 이상 보이지 않으면 '자리 비움'으로 전환한다.
- 상태가 바뀔 때마다 기존 블로그 API(/api_root/Post/)로 캡처 이미지와 함께 게시글을 등록한다
  (제목: '자리 비움' / '복귀', 본문: 사용자명·재석 시간). 얼굴 식별은 전부 PC에서 수행되고 서버로는 결과만 보낸다.
"""
import os
import pathlib
import time
from datetime import datetime

import cv2
import numpy as np
import requests

# 얼굴 검출용 Haar cascade: 레포에 동봉한 파일 우선, 없으면 OpenCV 내장 경로
CASCADE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'haarcascade_frontalface_default.xml')
if not os.path.exists(CASCADE):
    CASCADE = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'

# 한글 오버레이용 폰트 (Windows 맑은 고딕 / macOS / Linux 순으로 탐색, 없으면 영문 표기)
FONT_CANDIDATES = [r'C:\Windows\Fonts\malgun.ttf', '/System/Library/Fonts/AppleSDGothicNeo.ttc',
                   '/usr/share/fonts/truetype/nanum/NanumGothic.ttf']


def create_lbph():
    """OpenCV 4.x / 5.x 양쪽 API 지원."""
    face = cv2.face
    if hasattr(face, 'LBPHFaceRecognizer_create'):
        return face.LBPHFaceRecognizer_create()
    return face.LBPHFaceRecognizer.create()


def fmt(sec):
    sec = int(sec)
    return f'{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}'


class PresenceDetection:
    HOST = os.environ.get('BLOG_HOST', 'http://127.0.0.1:8000')
    username = os.environ.get('BLOG_USER', 'admin')
    password = os.environ.get('BLOG_PASS', 'password')
    ABSENT_SEC = float(os.environ.get('ABSENT_SEC', 30))   # 이 시간 이상 안 보이면 '자리 비움'
    THRESHOLD = float(os.environ.get('FACE_THRESHOLD', 70))  # LBPH 거리: 작을수록 유사 (보통 50~80)

    def __init__(self, token=None):
        self.enabled = False
        model = os.path.join('faces', f'{self.username}.yml')
        if not (hasattr(cv2, 'face') and os.path.exists(model)):
            print(f'[Presence] disabled: {model} 없음 (python enroll_face.py --name {self.username})')
            return
        self.recognizer = create_lbph()
        self.recognizer.read(model)
        self.detector = cv2.CascadeClassifier(CASCADE)
        self.token = token or self._login()
        self.font = self._load_font()
        self.present = False          # 현재 상태: True=재석, False=자리 비움
        self.since = time.time()      # 현재 상태가 시작된 시각
        self.last_seen = 0.0          # 등록 사용자가 마지막으로 보인 시각
        self.since_start = True       # 아직 한 번도 인식되지 않음
        self.enabled = True
        print(f'[Presence] enabled for {self.username} (absent after {self.ABSENT_SEC:.0f}s)')

    def _login(self):
        res = requests.post(self.HOST + '/api-token-auth/', {'username': self.username, 'password': self.password})
        res.raise_for_status()
        return res.json()['token']

    def _load_font(self):
        try:
            from PIL import ImageFont
            for path in FONT_CANDIDATES:
                if os.path.exists(path):
                    return ImageFont.truetype(path, 28)
        except ImportError:
            pass
        return None

    # ------------------------------------------------------------------
    def is_owner(self, frame, det, names):
        """person 박스 안에서 얼굴을 찾아 등록 사용자인지 판정 (얼굴 박스/라벨도 그림)."""
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
                cv2.putText(frame, f'{self.username if owner else "unknown"} {dist:.0f}', (x1 + fx, y1 + fy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                if owner:
                    return True
        return False

    def update(self, frame, det, names, save_dir):
        """매 프레임 호출: 상태 갱신 + 오버레이. 상태가 바뀌면 서버에 게시."""
        if not self.enabled:
            return
        now = time.time()
        seen = self.is_owner(frame, det, names)
        if seen:
            self.last_seen = now
        away_for = now - self.last_seen

        if not self.present and seen:
            first = self.since_start
            away = now - self.since
            self.present, self.since, self.since_start = True, now, False
            if first:
                self.post('재석 시작', f'{self.username} 인식됨 - 측정 시작', frame, save_dir)
            else:
                self.post('복귀', f'{self.username} 복귀 (자리 비움 {fmt(away)})', frame, save_dir)
        elif self.present and away_for > self.ABSENT_SEC:
            stayed = self.last_seen - self.since
            self.present, self.since = False, self.last_seen
            self.post('자리 비움', f'{self.username} 자리 비움 (재석 {fmt(stayed)})', frame, save_dir)

        if self.present:
            text, color = f'재석 {fmt(now - self.since)}', (0, 200, 0)
            if away_for > 2:
                text += f'  (미인식 {int(away_for)}s)'
        else:
            text, color = f'자리 비움 {fmt(now - self.since)}', (0, 0, 255)
        self.draw(frame, text, color)

    def draw(self, frame, text, color_bgr):
        if self.font is None:  # 한글 폰트 없으면 영문
            text = text.replace('재석', 'PRESENT').replace('자리 비움', 'AWAY').replace('미인식', 'unseen')
            cv2.putText(frame, text, (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color_bgr, 2)
            return
        from PIL import Image, ImageDraw
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        ImageDraw.Draw(img).text((10, 8), text, font=self.font, fill=color_bgr[::-1])
        frame[:] = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def post(self, title, text, frame, save_dir):
        """상태 변화 이벤트를 블로그 게시글로 등록 (changedetection.send 와 동일한 API)."""
        today = datetime.now()
        save_path = pathlib.Path(os.getcwd()) / save_dir / 'presence' / str(today.year) / str(today.month) / str(today.day)
        save_path.mkdir(parents=True, exist_ok=True)
        full_path = save_path / f'{today.hour}-{today.minute}-{today.second}-{today.microsecond}.jpg'
        cv2.imwrite(str(full_path), cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA))
        headers = {'Authorization': 'Token ' + self.token, 'Accept': 'application/json'}
        data = {'title': title, 'text': text, 'created_date': today, 'published_date': today}
        with open(full_path, 'rb') as f:
            res = requests.post(self.HOST + '/api_root/Post/', data=data, files={'image': f}, headers=headers)
        print(f'[Presence] {title}: {text} -> {res.status_code}')
