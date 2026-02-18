import cv2
import numpy as np
import pyautogui
import datetime
import os
import threading

class RecordingManager:
    def __init__(self):
        # 경로 설정
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.RELEASE_DIR = os.path.normpath(os.path.join(self.BASE_DIR, "../../", "release"))
        
        if not os.path.exists(self.RELEASE_DIR):
            os.makedirs(self.RELEASE_DIR)

        self.is_recording = False
        self.recording_thread = None

    def start_recording_threaded(self, filename_prefix="rec", fps=20.0):
        """메인 루프를 방해하지 않고 별도 스레드에서 녹화를 시작"""
        if self.is_recording:
            print("⚠️ 이미 녹화 중입니다.")
            return

        self.is_recording = True
        self.recording_thread = threading.Thread(
            target=self._recording_loop, 
            args=(filename_prefix, fps),
            daemon=True
        )
        self.recording_thread.start()

    def _recording_loop(self, filename_prefix, fps):
        """실제 캡처가 일어나는 내부 루프"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.mp4"
        full_path = os.path.join(self.RELEASE_DIR, filename)

        screen_size = tuple(pyautogui.size())
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(full_path, fourcc, fps, screen_size)

        print(f"🔴 녹화 스레드 시작 (저장: {full_path})")

        try:
            while self.is_recording:
                # 1. 화면 캡처
                img = pyautogui.screenshot()
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # 2. 파일 쓰기
                out.write(frame)

                # 3. CPU 점유율 조절 (FPS에 맞춤)
                # 이 부분이 없으면 무한 루프가 CPU를 100% 잡아먹습니다.
                pygame_wait = int(1000 / fps)
                cv2.waitKey(pygame_wait) 

        finally:
            out.release()
            print(f"⏹️ 녹화 종료 및 파일 저장 완료: {full_path}")

    def stop_recording_threaded(self):
        """녹화 루프를 안전하게 종료"""
        print("⏹️ 녹화 중지 요청...")
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join() # 스레드가 완전히 끝날 때까지 대기