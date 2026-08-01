# Hardware

기구·전자 설계 원본, BOM, 제작·조립 자료를 둡니다.

Markdown 문서를 제외한 이 디렉터리의 HYPERNOVA 하드웨어 설계는 별도 표기가 없으면 CERN-OHL-S-2.0을 적용합니다. 원본 위치는 `https://github.com/HyperNova26/hypernova-robot`입니다. 자세한 범위는 [라이선스 정책](../LICENSE.md)을 확인합니다.

## 예상 분류

- `mechanical/`: 기구 source, assembly, 도면, 제조 export
- `electrical/`: schematic, PCB, 배선도
- `bom/`: 기체·서브시스템별 BOM
- `manufacturing/`: 공정, 공차, 소재, jig와 검사 기록

## 기본 규칙

- native source와 제조·교환용 export를 구분합니다.
- assembly, part, COTS 부품, 도면의 이름 규칙을 함께 문서로 남깁니다.
- export 파일은 어떤 source revision과 도구 버전에서 나왔는지 알 수 있어야 합니다.
- 질량, 치수, 전압, 전류, torque 같은 물리량에는 단위를 적습니다.
- 대형 바이너리를 추가하기 전에 [저장소 정책](../docs/development/repository-policy.md)을 확인합니다.
