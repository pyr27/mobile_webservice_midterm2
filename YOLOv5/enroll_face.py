"""본인 얼굴 등록 스크립트 (온디바이스 얼굴 식별용 LBPH 모델 학습).

사용법:
    python enroll_face.py --name pyr            # 웹캠(0)에서 얼굴 30장 수집 후 faces/pyr.yml 저장
    python enroll_face.py --name pyr --source 1 # 다른 카메라

창이 뜨면 카메라를 정면으로 보고 조금씩 고개를 돌려 주세요. 's' 로 즉시 저장, 'q' 로 취소.
"""
import argparse
import os
import pathlib

import cv2
import numpy as np

FACE_SIZE = (200, 200)
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


def main(name, source, samples, interval):
    if not hasattr(cv2, 'face'):
        raise SystemExit('cv2.face 가 없습니다. 실행: pip uninstall -y opencv-python && pip install opencv-contrib-python')

    detector = cv2.CascadeClassifier(CASCADE)
    cap = cv2.VideoCapture(source)
    faces, count = [], 0
    while count < samples:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rects = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        for (x, y, w, h) in rects[:1]:  # 가장 먼저 잡힌 얼굴 1개만
            faces.append(cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE))
            count += 1
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, f'{name}: {count}/{samples}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, 'look at camera, turn head slowly  (s: save, q: quit)', (10, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.imshow('enroll_face', frame)
        key = cv2.waitKey(interval) & 0xFF
        if key == ord('q'):
            break
        if key == ord('s') and faces:
            break
    cap.release()

    if len(faces) < 5:
        cv2.destroyAllWindows()
        raise SystemExit(f'수집된 얼굴이 너무 적습니다 ({len(faces)}장). 조명을 밝게 하고 다시 시도하세요.')

    recognizer = create_lbph()
    recognizer.train(faces, np.zeros(len(faces), dtype=np.int32))  # label 0 = 본인
    out = pathlib.Path('faces')
    out.mkdir(exist_ok=True)
    recognizer.write(str(out / f'{name}.yml'))
    print(f'saved: {out / (name + ".yml")} ({len(faces)} samples)')

    # 수집한 얼굴 샘플 미리보기 + 저장 결과 화면 (키를 누를 때까지 유지)
    thumbs = [cv2.resize(f, (100, 100)) for f in faces[:10]]
    sheet = cv2.cvtColor(np.hstack(thumbs), cv2.COLOR_GRAY2BGR)
    banner = np.zeros((60, sheet.shape[1], 3), np.uint8)
    cv2.putText(banner, f'saved faces/{name}.yml  ({len(faces)} samples)  - press any key', (10, 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow('enroll_face', np.vstack([banner, sheet]))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True, help='서버 계정 username')
    ap.add_argument('--source', type=int, default=0)
    ap.add_argument('--samples', type=int, default=30)
    ap.add_argument('--interval', type=int, default=400, help='샘플 간격(ms)')
    a = ap.parse_args()
    main(a.name, a.source, a.samples, a.interval)