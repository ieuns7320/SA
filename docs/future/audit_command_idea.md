---
description: Slither 전처리 결과를 검토해서 감사 리포트를 생성한다 (API 호출 없이 이 세션 안에서 처리)
---

인자로 받은 경로의 프롬프트 파일(`$ARGUMENTS`)을 읽어라.

그 안에는 Slither 정적분석 finding 목록이 JSON으로 들어있다.

`docs/prompt_template_v1.md`를 먼저 읽고, 그 안의 시스템 프롬프트 규칙을 그대로
적용해서 각 finding을 검토하라:

1. 각 finding이 실제로 악용 가능한 true_positive인지, 방어 로직이 이미 있어서
   false_positive인지 판단한다. 확실하지 않으면 needs_review로 분류한다.
2. 코드 스니펫 범위 내에서 Slither가 놓친 이슈(접근 제어 누락 등)가 보이면
   additional_findings로 추가한다. 스니펫 밖의 코드는 추측하지 않는다.
3. `docs/prompt_template_v1.md`에 정의된 출력 JSON 스키마를 그대로 따른다.

결과는 다음 두 파일로 저장한다:
- `reports/<컨트랙트명>.audit.json` — 스키마를 따른 원본 JSON 응답
- `reports/<컨트랙트명>.audit.md` — 감사관이 바로 읽을 수 있는 사람 친화적 요약
  (심각도 순 정렬, 각 finding에 파일:라인 위치 명시)

저장 후 `overall_priority_order` 상위 3개를 채팅에 요약해서 보여줘라.
