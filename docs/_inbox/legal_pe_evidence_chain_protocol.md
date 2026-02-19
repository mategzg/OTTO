# Protocolo Perú: Preservación Probatoria y Cadena de Custodia

> **Objetivo:** asegurar admisibilidad, integridad, autenticidad y trazabilidad de evidencia para cobranza/controversias (prelitigio, litigio y arbitraje).

## 1) Principios rectores

- **Integridad:** el contenido no se altera desde su captura.
- **Autenticidad:** se puede demostrar origen y contexto.
- **Trazabilidad:** toda manipulación queda registrada.
- **Reproducibilidad:** tercero independiente puede verificar hash, fecha y fuente.
- **Minimización de riesgo:** acceso restringido y copias de respaldo controladas.

## 2) Roles mínimos

- **Custodio principal de evidencia:** responsable del repositorio y bitácora.
- **Responsable legal del caso:** define relevancia y estrategia probatoria.
- **Soporte TI/forense (si aplica):** extracción técnica y validación.
- **Aprobador de divulgación:** autoriza entrega a estudio, juzgado, árbitro o perito.

## 3) Cronograma de preservación (Día 0–30)

## Día 0–2: Legal Hold inmediato
- Emitir instrucción interna de **no borrar** correos, chats, archivos, backups, logs.
- Suspender políticas automáticas de purga en sistemas relevantes.
- Notificar a personal clave y obtener acuse.

## Día 1–5: Inventario y captura inicial
- Identificar fuentes: correo, WhatsApp/Teams, ERP/contabilidad, facturación, drive, dispositivos.
- Capturar exportaciones completas (no solo screenshots).
- Calcular hash (SHA-256) por archivo y consolidar manifiesto.

## Día 5–10: Normalización y clasificación
- Clasificar por: contrato, ejecución, facturación, requerimientos, reconocimientos, pagos.
- Marcar evidencia crítica para cautelar (riesgo de insolvencia, reconocimiento de deuda).
- Generar matriz de evidencia v1.

## Día 10–30: Robustecimiento para litigio
- Doble respaldo inmutable (local cifrado + nube con versionado).
- Declaraciones juradas/informes internos de responsables de captura.
- Preparación de anexos foliados y glosario de evidencias para demanda.

## 4) Flujo operativo estandarizado

1. **Identificación**
   - Registrar cada evidencia con ID único: `CASO-AÑO-TIPO-####`.
2. **Adquisición**
   - Captura en formato nativo + export alterno (PDF/CSV) cuando corresponda.
3. **Hash y sello temporal**
   - SHA-256 + fecha/hora (zona horaria documentada).
4. **Registro de custodia**
   - Bitácora de quién accede, cuándo, para qué, y qué acción realizó.
5. **Almacenamiento seguro**
   - Repositorio con control de permisos por mínimo privilegio.
6. **Uso procesal**
   - Toda copia para abogados/peritos sale con acta de entrega y hash de verificación.

## 5) Matriz de evidencia (campos mínimos)

- ID evidencia
- Descripción breve
- Fuente original
- Responsable de captura
- Fecha/hora captura
- Hash SHA-256
- Ubicación de almacenamiento
- Relevancia jurídica (alta/media/baja)
- Riesgo de impugnación
- Observaciones de autenticidad

## 6) Bitácora de cadena de custodia (formato sugerido)

| Fecha-hora | ID evidencia | Acción | Usuario | Motivo | Hash antes | Hash después | Observaciones |
|---|---|---|---|---|---|---|---|
| 2026-02-16 10:32 | CASO-2026-EMAIL-0001 | Ingesta inicial | legal.ops | Captura buzón | abc... | abc... | Sin alteración |
| 2026-02-16 11:05 | CASO-2026-EMAIL-0001 | Copia controlada | custodia | Envío a abogado externo | abc... | abc... | Acta #12 |

## 7) Protocolos específicos por tipo de evidencia

### 7.1 Correos electrónicos
- Exportar mensaje completo con headers.
- Guardar adjuntos en su formato original.
- No reenviar como método de conservación primaria.

### 7.2 Mensajería (WhatsApp/Teams/Slack)
- Preferir export de chat completo con metadata.
- Complementar con capturas de pantalla solo como apoyo.
- Registrar dispositivo, número/cuenta y fecha de extracción.

### 7.3 Documentos contractuales y facturación
- Conservar versión firmada y editable si existe.
- Registrar historial de versiones y aprobaciones.
- Integrar con libros/ERP para trazabilidad contable.

### 7.4 Evidencia financiera
- Estados de cuenta bancarios, constancias de transferencia, letras/pagarés.
- Validar correspondencia entre comprobante, asiento y obligación.

## 8) Preservación orientada a medidas cautelares

- Priorizar evidencia que pruebe:
  - existencia del crédito,
  - exigibilidad actual,
  - peligro en la demora (riesgo de vaciamiento/ocultamiento).
- Mantener carpeta cautelar separada con anexos listos para presentación urgente (<24h).

## 9) Control de acceso y seguridad

- Acceso por perfiles (legal, finanzas, TI) con permisos mínimos.
- Cifrado en reposo y en tránsito.
- Registro de auditoría activado.
- Prohibido compartir por canales informales sin acta y hash.

## 10) Gestión de incidentes

Si se detecta alteración, pérdida o fuga:
1. Activar alerta al responsable legal y custodio.
2. Congelar accesos y preservar logs.
3. Levantar acta de incidente con alcance e impacto.
4. Rehacer extracción desde fuente primaria.
5. Evaluar estrategia de saneamiento probatorio antes de presentar en proceso.

## 11) Checklist de salida a demanda/arbitraje

- [ ] Matriz de evidencia completa y actualizada.
- [ ] Hash verificado de anexos críticos.
- [ ] Bitácora de custodia sin vacíos temporales.
- [ ] Carpeta cautelar lista (si aplica).
- [ ] Actas de entrega a abogado/perito firmadas.
- [ ] Cronología de hechos consistente con evidencia.

## 12) Entregables internos recomendados

- `evidence_register.xlsx` (matriz maestra)
- `chain_of_custody_log.xlsx` (bitácora)
- `hash_manifest.txt` (huellas criptográficas)
- `legal_hold_notice.pdf` (instrucción de preservación)
- `litigation_bundle_index.pdf` (índice de anexos)
