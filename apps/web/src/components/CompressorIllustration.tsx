export function CompressorIllustration() {
  return (
    <svg className="machine" viewBox="0 0 390 260" role="img" aria-label="KO-3201 compressor illustration">
      <defs>
        <linearGradient id="compressor-body" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#477e70"/><stop offset="1" stopColor="#17493f"/></linearGradient>
        <filter id="compressor-shadow"><feDropShadow dx="0" dy="16" stdDeviation="10" floodOpacity=".18"/></filter>
      </defs>
      <ellipse cx="204" cy="229" rx="144" ry="18" fill="#b9c4c1" opacity=".35"/>
      <g filter="url(#compressor-shadow)" transform="translate(25 14)">
        <polygon points="48,162 186,102 325,150 188,217" fill="#9ebf37"/>
        <polygon points="48,162 188,217 188,230 48,175" fill="#67872a"/>
        <polygon points="188,217 325,150 325,164 188,230" fill="#b8d84e"/>
        <g transform="translate(63 69)">
          <polygon points="0,56 65,27 130,51 66,82" fill="#6ca08f"/>
          <polygon points="0,56 66,82 66,137 0,110" fill="url(#compressor-body)"/>
          <polygon points="66,82 130,51 130,107 66,137" fill="#236052"/>
          <ellipse cx="65" cy="28" rx="30" ry="13" fill="#dce5a0"/>
          <rect x="35" y="27" width="60" height="31" fill="#bed75a"/>
          <ellipse cx="65" cy="58" rx="30" ry="13" fill="#97b634"/>
          <ellipse cx="65" cy="27" rx="22" ry="9" fill="#213a36"/>
        </g>
        <g transform="translate(176 81)">
          <polygon points="0,48 59,22 112,42 54,71" fill="#568e7e"/>
          <polygon points="0,48 54,71 54,121 0,99" fill="#275d50"/>
          <polygon points="54,71 112,42 112,92 54,121" fill="#17473d"/>
          <rect x="45" y="6" width="24" height="39" rx="4" fill="#dce99c"/>
        </g>
        <g transform="translate(281 102)"><polygon points="0,27 31,13 52,21 22,36" fill="#dfe9a1"/><polygon points="0,27 22,36 22,80 0,70" fill="#aacb3a"/><polygon points="22,36 52,21 52,66 22,80" fill="#789c2c"/></g>
        <path d="M112 74c39-34 95-42 139-17" fill="none" stroke="#203e38" strokeWidth="12" strokeLinecap="round"/>
        <path d="M112 74c39-34 95-42 139-17" fill="none" stroke="#dfe8b0" strokeWidth="7" strokeLinecap="round"/>
      </g>
    </svg>
  );
}
