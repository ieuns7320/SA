# 1단계 MVP 프롬프트 템플릿 초안

전제: `preprocess_slither.py`로 정제한 JSON을 그대로 프롬프트에 주입한다.
노이즈성 detector는 이미 걸러졌고, 각 finding에 코드 스니펫이 붙어 있는 상태.

---

## System prompt

```
당신은 스마트컨트랙트 보안 감사관을 보조하는 시니어 보안 엔지니어입니다.
정적분석 도구(Slither)가 탐지한 결과를 검토하고, 감사관이 빠르게 판단할 수 있도록
자연어로 설명하고 우선순위를 매기는 것이 임무입니다.

규칙:
1. 각 finding에 대해 "실제로 악용 가능한 취약점인지" 여부를 판단하세요.
   Slither는 오탐률이 높은 도구입니다. 코드 맥락을 보고 방어 로직
   (예: onlyOwner modifier, require문, checks-effects-interactions 패턴)이
   이미 존재한다면 위험도를 낮추거나 오탐으로 분류하세요.
2. 확실하지 않으면 추측하지 말고 "확인 필요"로 표시하세요. 없는 근거를
   지어내지 마세요.
3. 정적분석 도구가 놓쳤을 수 있는 이슈(접근 제어 누락, 비즈니스 로직 오류 등)를
   전달된 코드 스니펫 범위 내에서 발견하면 "additional_findings"에 추가하세요.
   단, 전달되지 않은 코드에 대해서는 추측하지 마세요.
4. 각 finding은 아래 JSON 스키마로만 응답하세요. 스키마 외 텍스트는 금지합니다.

출력 스키마:
{
  "reviewed_findings": [
    {
      "id": "<입력의 id 그대로>",
      "verdict": "true_positive" | "false_positive" | "needs_review",
      "severity_adjusted": "Critical" | "High" | "Medium" | "Low" | "Informational",
      "explanation": "<2-3문장. 왜 위험한지/왜 오탐인지, 개발자가 이해할 수 있는 언어로>",
      "exploit_scenario": "<가능하다면 공격이 실제로 어떻게 일어나는지 1-2문장. 아니면 null>",
      "suggested_fix": "<구체적인 수정 방향 1-2문장>"
    }
  ],
  "additional_findings": [
    {
      "description": "<Slither가 놓친 이슈 설명>",
      "location": "<함수명 또는 라인 범위>",
      "severity": "Critical" | "High" | "Medium" | "Low",
      "reasoning": "<왜 이게 문제인지>"
    }
  ],
  "overall_priority_order": ["<id 또는 additional_findings 설명을 심각도 순으로 나열>"]
}
```

---

## User prompt (템플릿)

```
다음은 컨트랙트 `{contract_file}`에 대한 정적분석 결과입니다.
총 {total_findings}개의 finding이 있습니다.

{findings_json}

위 finding들을 검토하고, 시스템 프롬프트의 스키마에 맞춰 응답하세요.
```

`{findings_json}`에는 `preprocess_slither.py` 출력의 `findings` 배열을 그대로 넣습니다.

---

## 실제 샘플로 채운 예시 (VulnerableVault.sol 기준)

User 메시지에 실제로 들어가는 내용:

```
다음은 컨트랙트 `VulnerableVault.sol`에 대한 정적분석 결과입니다.
총 4개의 finding이 있습니다.

[
  {
    "id": "arbitrary-send-eth-30",
    "check": "arbitrary-send-eth",
    "impact": "High",
    "confidence": "Medium",
    "lines": "30-33",
    "summary": "VulnerableVault.ownerWithdrawAll() sends eth to arbitrary user",
    "code_snippet": "30: function ownerWithdrawAll() external {\n31:   require(tx.origin == owner, \"Not owner\");\n32:   payable(owner).transfer(address(this).balance);\n33: }"
  },
  {
    "id": "reentrancy-eth-17",
    "check": "reentrancy-eth",
    "impact": "High",
    "confidence": "Medium",
    "lines": "17-22",
    "summary": "Reentrancy in VulnerableVault.withdraw(uint256)",
    "code_snippet": "17: function withdraw(uint256 amount) external {\n18:   require(balances[msg.sender] >= amount, ...);\n19:   (bool success, ) = msg.sender.call{value: amount}(\"\");\n20:   require(success, \"Transfer failed\");\n21:   balances[msg.sender] -= amount;\n22: }"
  },
  {
    "id": "tx-origin-30",
    "check": "tx-origin",
    "impact": "Medium",
    "confidence": "Medium",
    "lines": "30-33",
    "summary": "ownerWithdrawAll() uses tx.origin for authorization"
  },
  {
    "id": "missing-zero-check-25",
    "check": "missing-zero-check",
    "impact": "Low",
    "confidence": "Medium",
    "lines": "25-26",
    "summary": "setOwner(address).newOwner lacks a zero-check",
    "code_snippet": "25: function setOwner(address newOwner) external {\n26:   owner = newOwner;\n27: }"
  }
]

위 finding들을 검토하고, 시스템 프롬프트의 스키마에 맞춰 응답하세요.
```

이 입력에 대해 기대하는 LLM의 판단 방향 (검증용 기준):

- `reentrancy-eth-17`: **true_positive, Critical로 상향.** 외부 호출(`call`) 후에
  `balances`를 차감하는 전형적인 checks-effects-interactions 위반. 실제 악용 가능.
- `arbitrary-send-eth-30` / `tx-origin-30`: 같은 함수에 대한 두 개의 별개 finding이지만
  근본 원인은 하나(`tx.origin` 인증). LLM이 이 둘을 하나의 이슈로 묶어서 설명하면 이상적.
  tx.origin 인증은 피싱 컨트랙트를 통한 우회가 가능하므로 **true_positive, High**.
- `missing-zero-check-25`: Slither는 "zero-check 없음"만 지적했지만, **진짜 문제는
  `setOwner`에 접근 제어(onlyOwner)가 아예 없다는 것.** 이 부분을 LLM이
  `additional_findings`에서 "Critical, 누구나 owner를 탈취할 수 있음"으로 잡아내는지가
  이 프롬프트 설계의 핵심 검증 포인트.

---

## 다음에 확인해야 할 것

1. 실제 API 호출로 위 프롬프트를 돌려서 `setOwner` 접근 제어 누락을
   `additional_findings`에서 잡아내는지 확인 (핵심 성공 기준)
2. `arbitrary-send-eth`와 `tx-origin`을 중복 없이 하나로 묶어 설명하는지 확인
3. JSON 스키마를 안정적으로 지키는지 (temperature, response_format 등 조정 필요할 수 있음)
4. false positive 유도 테스트: 이미 `onlyOwner`가 걸려있는 정상 코드를 넣어서
   verdict가 false_positive로 나오는지 확인
