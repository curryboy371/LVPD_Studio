탁월한 선택입니다. 긴 텍스트를 통째로 변환하면 타임스탬프와 미세하게 어긋나는 고질적인 문제가 발생하지만, 문장(자막) 단위로 끊어서 음성을 만들고 그 음성 길이에 맞춰 자막을 띄우면 싱크가 100% 완벽하게 일치하게 됩니다.

이 방식을 구현하려면 오디오 생성 지연(랙)으로 인해 화면 녹화가 끊기지 않도록 재생 전 모든 음성을 미리 생성(Pre-generation)해 두고 순차적으로 재생하는 것이 가장 좋습니다.

아래는 원래 자막 파일의 시간은 무시하고, 생성된 TTS 음성의 실제 길이를 기준으로 화면과 소리를 완벽히 맞춰주는 파이썬 코드입니다.

🛠️ 구현 방법: 완벽 싱크 자동 맞춤 플레이어
필요한 라이브러리(gtts, pygame, pysrt)가 설치되어 있어야 합니다. 크로마키(녹색 배경) 모드로 작성하여 영상 편집 시 배경을 날리기 좋게 만들었습니다.

Python
import pygame
import pysrt
import sys
import os
from gtts import gTTS

def auto_sync_tts_player(srt_path):
    # 1. 자막 파일 로드
    print("자막 파일을 읽는 중...")
    subs = pysrt.open(srt_path, encoding='utf-8')
    
    audio_files = []
    texts = []
    
    # 2. 자막별 TTS 오디오 일괄 사전 생성 (녹화 중 끊김 방지)
    print("TTS 음성 파일을 생성하고 있습니다. 잠시만 기다려주세요...")
    for i, sub in enumerate(subs):
        text = sub.text.replace('\n', ' ').strip()
        if not text:
            continue
            
        temp_mp3 = f"temp_tts_{i}.mp3"
        
        # gTTS로 한국어 음성 생성 (원하는 다른 TTS API로 교체 가능)
        tts = gTTS(text=text, lang='ko')
        tts.save(temp_mp3)
        
        audio_files.append(temp_mp3)
        texts.append(text)
        print(f"[{i+1}/{len(subs)}] 생성 완료: {text}")

    # 3. Pygame 초기화 및 화면 설정
    pygame.init()
    pygame.mixer.init()
    
    SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 720
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("자동 싱크 자막 플레이어 (크로마키 화면)")
    
    # 시스템 폰트 설정 (윈도우: 맑은 고딕)
    try:
        font = pygame.font.SysFont("malgungothic", 60, bold=True)
    except:
        font = pygame.font.Font(None, 60)
        
    clock = pygame.time.Clock()

    print("\n준비 완료! 재생을 시작합니다. 화면 녹화 프로그램을 실행해 주세요.")
    
    # 4. 순차 재생 메인 루프
    for i in range(len(audio_files)):
        current_text = texts[i]
        current_audio = audio_files[i]
        
        # 오디오 로드 및 재생
        pygame.mixer.music.load(current_audio)
        pygame.mixer.music.play()
        
        # 해당 오디오가 재생되는 동안만 화면에 자막 렌더링
        while pygame.mixer.music.get_busy():
            # 이벤트 처리 (창 닫기 등)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    _cleanup_files(audio_files)
                    sys.exit()
            
            # 크로마키용 녹색 배경 (원하면 (0, 0, 0) 검은색으로 변경)
            screen.fill((0, 255, 0))
            
            # 자막 텍스트 렌더링 (흰색 글씨)
            text_surface = font.render(current_text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 100))
            screen.blit(text_surface, text_rect)
            
            pygame.display.flip()
            clock.tick(30) # 30 프레임 유지
            
    print("모든 재생이 완료되었습니다.")
    
    # 5. 종료 및 임시 파일 정리
    pygame.mixer.music.unload() # 파일 점유 해제
    pygame.quit()
    _cleanup_files(audio_files)

def _cleanup_files(file_list):
    """생성했던 임시 mp3 파일들을 삭제합니다."""
    for file in file_list:
        try:
            if os.path.exists(file):
                os.remove(file)
        except Exception as e:
            pass

# 실행 예시
# auto_sync_tts_player("my_subtitle.srt")
💡 코드의 핵심 포인트
사전 생성(Pre-generation): 인터넷을 통해 TTS를 가져오는 시간을 재생 루프와 분리했습니다. 재생 중에 실시간으로 생성하면 네트워크 지연이 발생할 때 오디오와 영상이 끊기며 녹화본이 망가질 수 있기 때문입니다.

pygame.mixer.music.get_busy() 활용: 오디오가 재생 중인지 확인하는 함수입니다. 이 함수가 True를 반환하는 동안에만 해당 자막을 띄워두기 때문에, 오디오 길이가 1초든 10초든 완벽하게 자막 표시 시간이 자동으로 맞춰집니다. 원본 SRT 파일의 시작/종료 시간은 전혀 필요하지 않습니다.

자동 정리(Cleanup): 녹화가 끝나고 프로그램이 종료될 때, 중간에 쪼개서 만들었던 수십, 수백 개의 temp_tts_*.mp3 파일들을 자동으로 지워주어 하드디스크 용량을 차지하지 않게 합니다.

---

## LVPD 숏츠 통합 (문장 테이블 + shorts ID 참조)

1. **`ko_narration_sets`** — 세트 id·(선택) srt_path  
2. **`ko_narration_lines`** — `set_id`, `seq`, `text` (문장 1행 = TTS 1큐)  
3. **`shorts_*_clips.ko_narration_id`** — 위 세트 id 입력  
4. **배치(재생 전 필수)**  
   ```bash
   python main.py batch-shorts-ko --shorts-type conversation --topic where
   ```
   - 산출: `resource/sound/ko_set_{set_id}_{n}.mp3`  
   - 메타: `resource/sound/ko_set_{set_id}_timeline.json`  
5. **숏츠 재생** — 문장 mp3 순차 재생 + 재생 중인 문장만 하단 자막 (`get_busy()` 동일 원리).