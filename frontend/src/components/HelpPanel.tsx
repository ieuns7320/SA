export function HelpPanel() {
  return (
    <div className="help-panel">
      <div className="help-panel-inner">
        <ol className="help-steps">
          <li>
            <span className="help-step-num">1</span>
            <span>
              <strong>컨트랙트 주소</strong>(0x...) 또는 <strong>.sol 파일</strong>을
              입력하세요.
            </span>
          </li>
          <li>
            <span className="help-step-num">2</span>
            <span>
              <strong>분석 시작</strong>을 누르면 Slither 정적분석이 백그라운드에서
              실행됩니다. 컨트랙트 크기에 따라 최대 2분 정도 걸릴 수 있어요.
            </span>
          </li>
          <li>
            <span className="help-step-num">3</span>
            <span>
              완료되면 자동으로 <strong>리포트 화면</strong>으로 이동합니다.
            </span>
          </li>
        </ol>
        <p className="help-note">
          로그인 없이 익명으로 사용할 수 있어요. 리포트는{" "}
          <strong>LLM 판단 없이</strong> Slither 정적분석 결과를 규칙 기반으로 정리해서
          보여주는 것이며, 최종 판단은 직접 검토해야 합니다.
        </p>
      </div>
    </div>
  );
}
