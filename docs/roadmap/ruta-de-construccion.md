=====================================================
DATARA 2 — RUTA DE CONSTRUCCIÓN
Guardado: 04/09/2026 · Actualizada: 10/11/2026 — **F2 ✓ PRUEBA DE EMPAQUETADO: CERRADA Y EN `main`** (el .exe de escritorio existe y corre: prueba T7 9/9 en la máquina del maintainer, entrega en 5 PRs encadenados #23-#27, revisión nativa del Job Object APROBADA, y `main` @ 9bd8c56 con los 9 commits restaurados en la historia). **La Ruta entró al repo** (`docs/roadmap/ruta-de-construccion.md`, `a21eacf`). **PRÓXIMO: el hardening** (los 9 advisories del review de F2 + F9). ESTADO ANTERIOR (03/11/2026): **PERFIL: SIETE OBRAS CERRADAS Y PUSHEADAS (T7a preferencias, T3 eliminación con gracia, T2 sesiones activas, T6 panel de consumo, T5 bitácora personal, T4 export de la cuenta, T1 nombre editable); QUEDA SOLO T7b (repintado Dark Cockpit)**. **PULIDO DEL REGISTRO ✓ COMPLETO** (seguridad de auth ✓ + experiencia del alta ✓ + términos de uso ✓, todo en `main`). **VERIFICACIÓN DE CORREO + RECUPERACIÓN DE CONTRASEÑA ✓ ENTREGADAS** — primera infraestructura de correo de Datara, en la rama `feat/email-verification-recovery` **PUSHEADA Y **MERGEADA A `main` VÍA PR #22** (`7300598`, squash: los 6 work units quedaron como un solo commit en `main`)**; entrega REAL validada en vivo por el maintainer (Gmail, 587/STARTTLS) y revisión nativa aprobada en los dos cortes riesgosos. `main` @ 207879c. **PRÓXIMO: el BLOQUE DE FUNCIONALIDAD PRE-REPINTADO (sección nueva más abajo); el repintado T7b queda ÚLTIMO por decisión del 03/11: primero TODA la funcionalidad, cero cirugía plástica hasta que la funcionalidad esté lista**. Lo que sigue es el estado al 26/10/2026, conservado como historia: (SECCIÓN PERFIL: **T7a PREFERENCIAS ✓ ENTREGADA, PUSHEADA Y VALIDADA EN VIVO** — la ronda de alcance de T7 partió la obra en DOS por el método del maintainer ("mi metodo es primero funcionalidad y luego cirugia plastica"): **T7a preferencias del perfil** (funcional) y **T7b repintado Dark Cockpit** (cosmético, ÚLTIMO). ORDEN NUEVO: T7a ✓ → T3 → T2 → T6 → T5 → T4 → T1 → T7b. ENTREGADO EN T7a: cuatro preferencias por usuario (números es/internacional, fechas relativa/absoluta, símbolo de moneda —sin conversión: el costo es USD— y comportamiento al abrir), migración 0006 (columnas nullable en user_settings), GET/PUT /api/settings con valores efectivos, card Preferencias en Perfil con botón Restablecer, y el formato inyectado en CADA llamada del chat (prompt principal, reparación, segunda pasada y post-procesador de números). main @ fcb2047 (`a4d602d` backend + `610b1bc` chat + `8f91759` frontend + `fcb2047` fix del chat), pusheado 21bcd25..fcb2047; fichas odd/tasks/profile-preferences.md + odd/tasks/profile-roadmap.md. FIX DE LAYOUT DEL CHAT ✓ (fcb2047, ajeno a T7a): el chat quedaba más ancho que la ventana (scroll horizontal permanente); NO era zoom (probado a 100%). Causa: la columna del chat no podía encogerse (`minWidth: 0`) y un gráfico de plotly conservaba un ancho en píxeles viejo. REVIEW NATIVO DEL CANDIDATO T7a: el START sobre /mnt/c falló con `candidate-view checkout-index timeout` (defecto de 9p ya reportado, lineage_created=false); se probó DESDE UN CLON EN EXT4 y materializó → envelope de consentimiento relayado → el maintainer eligió "Skip this time" (declined_this_candidate): candidato SIN review POR DECISIÓN EXPLÍCITA, con verificador independiente (todos los ítems PASS) + validación en vivo. PRÓXIMO: **T3** (eliminar cuenta con gracia de 7 días cancelable, migración 0007). PENDIENTES de siempre: B5 (deuda de review/proceso), los 17 advisories del perfil, AGENTS.md desactualizado (dice ~357/~88; hoy 788/569) y dos avisos cosméticos del verificador de T7a. SETTINGS ✓ CERRADA Y FUSIONADA (main @ 642fbe5, PR #21); SECCIÓN ANÁLISIS ✓ CERRADA (A4 ✓ cb6c5e9 + e0d2d14, A3 ✓ 0c4d9a8, A2 ✓ e3d6901, A1 ✓); Wizard ✓; SECCIÓN FILES ✓ CERRADA)
(estados al cierre del diseño visual — FASE 1 COMPLETA)
Fuente: "Datara 2 - Objetivos del proyecto.txt" +
        estado real del repo al 04/09/2026
=====================================================

CÓMO LEER ESTE ARCHIVO
- Es la ruta desde los cimientos (lo ya construido y validado)
  hasta cumplir los 6 objetivos de la visión.
- Estados: ✓ HECHO | ◐ PARCIAL | ✗ PENDIENTE
- Lo que no está acá no existe: toda feature nueva entra por
  acá primero. Actualizar estados al cerrar cada fase.

─────────────────────────────────────────────
DÓNDE ESTAMOS HOY (10/11/2026 — **F2 ✓ CERRADA: el .exe de escritorio ya existe y corre en la máquina del maintainer** (prueba T7 9/9, 5 PRs encadenados #23-#27, revisión nativa del Job Object aprobada, `main` @ 9bd8c56); **la Ruta entró al repo** y pasa a ser la fuente de verdad (`docs/roadmap/ruta-de-construccion.md`, `a21eacf`); **PRÓXIMO: el hardening** (ver abajo; el repintado T7b sigue ÚLTIMO). CÓMO ESTÁBAMOS EL 03/11/2026 — **siete obras del perfil cerradas; queda SOLO T7b**; el pulido del registro completo (seguridad + experiencia + términos); **verificación de correo + recuperación ✓ entregadas y **MERGEADAS a `main` vía PR #22** (`7300598`, 03/11 22:06 UTC)**, con entrega real validada en Gmail; `main` @ 7300598; **PRÓXIMO: el bloque de funcionalidad pre-repintado (sección nueva más abajo); el repintado T7b va ÚLTIMO** y decidir el merge de la rama del correo). CÓMO ESTÁBAMOS EL 26/10/2026 — SECCIÓN PERFIL: **T7a PREFERENCIAS ✓ ENTREGADA, PUSHEADA Y VALIDADA EN VIVO**. El orden del backlog pasó a **T7a ✓ → T3 → T2 → T6 → T5 → T4 → T1 → T7b** (el repintado Dark Cockpit quedó ÚLTIMO por el método del maintainer: funcionalidad primero, cirugía después). main @ fcb2047, pusheado 21bcd25..fcb2047; fichas odd/tasks/profile-preferences.md y odd/tasks/profile-roadmap.md. Además: FIX DE LAYOUT DEL CHAT ✓ (fcb2047). PRÓXIMO: T3 (eliminar cuenta con gracia de 7 días cancelable, migración 0007). SETTINGS ✓ CERRADA Y FUSIONADA (main @ 642fbe5, PR #21); SECCIÓN ANÁLISIS ✓ CERRADA: A4 ✓ CERRADO (sesión 21, cb6c5e9 + e0d2d14, ciclo de vida completo: Reabrir sesión viva + fallback snapshot, Exportar Markdown, renombrar, borrar, paginación keyset); A3 ✓ CERRADO (sesión 20, 0c4d9a8); A2 ✓ (sesión 19, e3d6901); A1 ✓; Wizard ✓; SECCIÓN FILES ✓ CERRADA)
─────────────────────────────────────────────
=====================================================
BLOQUE DE FUNCIONALIDAD PRE-REPINTADO (decidido el 03/11/2026)
El repintado Dark Cockpit (T7b) queda ÚLTIMO: primero TODA la
funcionalidad. Este es el camino, en orden.
=====================================================

DECISIONES DE FORMA (cerradas con el maintainer, 03/11):
- PRODUCTO: **EJECUTABLE** que corre en la PC del analista, en **VENTANA
  PROPIA** (no pestaña del navegador). Página hospedada: quizá a futuro;
  el mismo código sirve para las dos, lo que cambia es la identidad y la
  configuración. La estética imaginada para esa ventana es "estilo
  ChatGPT CLI": eso es CIRUGÍA, se decide en T7b, no ahora.
- IDENTIDAD: **perfil local** en el primer arranque, sin correo. Las
  pantallas de registro / verificación / recuperación **se OCULTAN** en
  modo local y **se conservan en el código** para un futuro hospedado.
- MODELOS LOCALES: **DESCARTADOS** (la máquina de un analista real no los
  sostiene; medido: 16 GB de RAM y 4 GB de VRAM dan techo en el escalón
  7-8B con paciencia). Se trabaja con **proveedores**.
- PRIMER ARRANQUE: pantalla de bienvenida **estilo tutorial** (elegir
  carpeta de datos, proveedor, clave y modelo, y decir con claridad qué
  va a salir de la máquina) + **animación con el logo de Datara**.
- PRIVACIDAD DECLARADA: niveles de privacidad por archivo/sesión + un
  **visor de "esto es lo que se envía"**. Nada de marketing "100%
  privado": se dice qué sale, cuándo y a quién.

TAREAS, EN ORDEN:
| F1 | **Identidad local**: perfil local + bloqueo opcional; ocultar las pantallas de correo en modo local (dejarlas listas para el hospedado); adaptar el sidebar y la card Sesión | ✗ |
| F2 | **Prueba de empaquetado**: el .exe con PyInstaller/Nuitka RESOLVIENDO el sandbox (hoy lanza `python server/sandbox_runner.py` como subproceso y en un binario congelado `sys.executable` es el .exe, no un Python); medir tamaño y primer arranque; probar la ventana propia (webview) | ✓ CERRADA 06/11 |
| F2-advisories | **Los 9 hallazgos del review del Job Object** (trabajo posterior, NINGUNO bloqueó la entrega): el más serio es que el sandbox **falla ABIERTO** — si el Job Object no se crea o no se asigna, el código del modelo corre SIN límites y solo queda un warning (`sandbox_local.py:121-127`, `:113-127`, `:141-143`); más el tope de CPU no aplicado en Windows (`sandbox_runner.py:51-58`), huecos de límites (`sandbox_win_job.py:197-205`), `ActiveProcessLimit=1` incompatible con `--onefile` (`:203`), errores Win32 sin exponer, y dos tests flojos (camino congelado; `import resource` sin condicionar, que no corre en Windows) | ✓ CERRADA 10/11/2026 (slices 1-3: PR #28, #29, #30) |
| F3 | **Carpeta de datos**: ubicación por sistema operativo y **fuera de cualquier carpeta sincronizada** (OneDrive/Dropbox) | ✗ |
| F4 | **Primer arranque / tutorial**: pantalla de bienvenida con la animación del logo | ✗ |
| F5 | **Multi-dataset (FASE 2)**: cruce de varios archivos a la vez. VA ANTES DEL REPINTADO porque cambia la pantalla del chat | ✗ |
| F6 | **Privacidad declarada**: niveles por archivo/sesión + visor de "esto se envía" + perillas (modo solo-esquema, valores enmascarados con su forma, agregados en vez de detalle, alias de columnas) | ✗ |
| F7 | **Estados de UI**: vacío / error / cargando de cada pantalla | ✗ |
| F8 | **Firma y actualización**: firma de código (o SignPath para proyectos abiertos) y política de auto-actualización | ✗ |
| F9 | **Hardening de auth para el hospedado**: protección de `Origin`/CSRF (también protege el localhost del .exe), flag `Secure` en la cookie, freno de intentos persistente, tope en los endpoints de token, correos de aviso, y la clave del proveedor cifrada con el llavero del sistema | ✗ |
| T7b | **REPINTADO Dark Cockpit** | **ÚLTIMO**, cuando la funcionalidad esté completa | ✗ |

**F2 ✓ CERRADA (06/11/2026): el envase NO invalidó el plan.** El .exe existe y
corre: prueba T7 9/9 en la máquina del maintainer (el punto crítico, el sandbox
con Job Object, incluido), entrega en 5 PRs encadenados (#23-#27), revisión
nativa APROBADA del commit riesgoso (`3e5f858`), y `main` @ `9bd8c56` con los 9
commits restaurados en la historia. Deuda anotada: el empaquetado dejó una lista
de advisories (fila F2-advisories, arriba).

**PRÓXIMA SESIÓN: el HARDENING, en dos frentes.** (1) **F2-advisories**: los 9
hallazgos del review de F2, encabezados por el más serio — el sandbox **falla
ABIERTO**: si el Job Object no se crea o no se puede asignar, el código del modelo
corre SIN límites y solo queda un warning en el log; debería negarse a ejecutar
(fail-closed). (2) **F9**: el hardening de auth del hospedado, tal como lo define
la tabla de arriba (Origin/CSRF, cookie `Secure`, freno persistente, tope en los
endpoints de token, correos de aviso, clave del proveedor en el llavero del SO).
El orden entre los dos frentes queda a decidir por el maintainer.

**ACTUALIZADO 10/11/2026: F2-advisories ✓ CERRADO** (slices 1-3: PR #28 en
`main`, PR #29 en `main`, PR #30 abierto al cierre de la sesión). Los 9
advisories del review del Job Object quedaron cerrados, más las higienes H1 y H2.
**PRÓXIMO FRENTE: F9 — hardening de auth para el hospedado.**

- FASE 0 (cimientos): COMPLETA — 8 rondas de QA cerradas verdes.
- FASE 1 (pulir el núcleo): ✓ COMPLETA (15/09) — cinturón ✓,
  realtime ✓, cancelar subida ✓ + reintentos ✓ (Ronda 5),
  RIGOR mov1+mov2 ✓ (Ronda 6, bench Q1-Q11 11/11), bug de
  orden ✓, WIZARD FIRST-RUN ✓ (Movimiento 3, Ronda 7),
  SETTINGS WIZARD DE PROVEEDORES ✓ (SDD settings-provider-
  wizard: PRs #6-#13 mergeados; Ronda 8 A-G verde con F1
  diferido; buscador de modelos 6af03c0 — main @ 6af03c0),
  DISEÑO VISUAL ✓ (15/09: 18 pantallas canónicas en /Pantallas).
- FASE 1.5 (pulido por sección) — SECCIÓN CHAT: ✓ CERRADA
  (23/09). Las 7 tareas del backlog + el pulido cross-tab
  (is_streaming en la lista, adjuntar desde el composer, editar
  pregunta → truncar + re-preguntar con Regenerar, eventos de
  ciclo de vida de sesión CREATED/UPDATED/DELETED) quedaron
  implementadas, validadas EN VIVO por el usuario y pusheadas a
  main. El change chat-robustez (taxonomía de errores) ya está en
  main. Main @ 0b70605 (24/09, sesión 5).
- FASE 1.5 (pulido por sección) — SECCIÓN FILES: ✓ CERRADA
  (01/10). TIER 0-4 ✓ + F14 ✓ CERRADO 29/09 (lista por sesión).
  Inventario funcional COMPLETO + triage en 4 tiers.
  TIER 0 ✓ (F1 límites de subida, F1.1 guard de body); TIER 1 ✓
  (F2 UNIQUE de nombre, F3 Excel multi-hoja); TIER 2 ✓ (F4
  confirmación de delete, F5 abort del wizard, F6 mismatch .tab,
  F7 tipo del cliente); TIER 3 ✓ (F8 perfilado offloaded, F9
  vista de perfil tabulada, F10 paginación con cursor); TIER 4 ✓
  (F11 descarga del original ✓ CERRADO 29/09; F12 rename de archivo
  ✓ CERRADO 29/09 + su follow-up de unicidad case-insensitive; F13
  nits de tablas ✓ CERRADO 29/09; F14 lista por sesión ✓ CERRADO
  29/09) + notas transversales. Commits por
  ítem en la sección Files de abajo y en el REGISTRO DE HITOS. OJO: la
  revisión RDD de NINGÚN candidato de Files pudo completarse por
  el defecto de transport #4030 → todos con fallback RDD-off
  (verificador independiente) + validación EN VIVO antes del push
  (F13: el usuario eligió "Saltear esta vez", decline candidate-scoped).
- TIER 1 F2 (UNIQUE de nombre por sesión) ✓ CERRADO (24/09,
  sesión 6): migración 0003 (dedupe conservando el id más bajo +
  purga de profiles huérfanos + CREATE UNIQUE INDEX
  idx_files_unique_name) y IntegrityError→409 con el MISMO texto
  que el pre-check (helper compartido para que no divergan). El
  path del INSERT NO desvincula el archivo: ese storage_path es
  del que ganó la race, borrarlo destruiría su archivo. Rama
  feat/files-f2-unique-dedupe mergeada ff a main (1d5acf7,
  0b70605..1d5acf7), 7 archivos +190/-33; suite backend 601/601;
  validado EN VIVO por el usuario. Migración verificada sobre una
  COPIA de la DB real: versiones 1,2 → 1,2,3, índice presente, los
  2 archivos reales intactos, INSERT duplicado rechazado.
  La revisión RDD de F2 tampoco corrió: el preflight sin selector
  ya ve el worktree vacío (todo commiteado, paths: []) y su único
  paso pendiente era declarar scope de untracked (ruido: Pantallas/,
  odd/, openspec/), no el commit. Se suma el mismo defecto #4030.
- TIER 1 F1.1 (guard de body acotado al upload) ✓ CERRADO (24/09,
  sesión 7): middleware ASGI puro scoped a POST
  /api/sessions/{id}/files que rechaza por Content-Length ANTES de
  que Starlette parsee/spoolee el multipart — 413 sobre max+margen,
  411 si falta Content-Length (cierra el bypass chunked), 400 si
  viene malformado. Cierra el residual de F1, incluido el camino NO
  autenticado (antes: 401 DESPUÉS de escribir en /tmp). Commiteado y
  pusheado (1a093df, 1d5acf7..1a093df), 5 archivos +243/-16; focused
  files 44/44, suite backend 603/603; validado EN VIVO por el usuario.
- FASE 1.5 (pulido por sección) — SECCIÓN SETTINGS: ✓ CERRADA
  (15/10, main @ c1c2037). El plan `settings-production-readiness`
  quedó COMPLETO: WU1-WU5 + el backlog post-WU5 B1-B6, en 10
  unidades de trabajo, todas verificadas, validadas EN VIVO por el
  maintainer y pusheadas. WU1 hub editable (7ccd1cc); WU2 guardar-y-
  verificar (db2b9f4); WU3 whitelist + acción en el banner (08f54d4);
  WU4 copy español (2b6c6bf); WU5 capa "a prueba de tontos" (496d60e);
  B1 gate provider-aware D6 (e56e0aa); B2 catálogo/guías por proveedor
  (0d094b8); B2-advisories pricing provider-aware + priceLabel
  (39aa921); B3 timeout del probe en el cliente (8325eab); B4 copy del
  rechazo SSRF + precio de llama-3.3-70b (b0940a6 + a6be79e); B6
  guardián del gate duplicado + cobertura (31017c5 + d6ae7ad + c1c2037).
  Reviews nativas APROBADAS en WU1/WU2/WU4/B1/B2; SIN review en WU3
  (quedó en correction_required sin receipt por el transport), WU5
  (#4655 rompió el STATUS atado), B2-advisories, B3, B4 y B6 → entrega
  por política ordinaria del repo.
- PERFIL — T7a PREFERENCIAS ✓ ENTREGADA Y PUSHEADA (26/10, sesión 24).
  La sección nació el 19/10 (sesión 22) con una primera entrega validada EN VIVO —
  ver la cuenta, cambiar la contraseña (cerrando las demás sesiones) y cerrar
  sesión, entrando desde el bloque de usuario del sidebar (main @ 711cf2a; ficha
  odd/tasks/profile-section.md). FUNCIONES ✓ DECIDIDAS (19/10, sesión 23).
  LA RONDA DE ALCANCE DE T7 SE HIZO (26/10, sesión 24) y partió la obra en DOS por
  el método del maintainer (funcionalidad primero, cirugía después): **T7a
  preferencias del perfil** (funcional) y **T7b repintado Dark Cockpit**
  (cosmético, ÚLTIMO). ORDEN NUEVO: T7a ✓ → T3 → T2 → T6 → T5 → T4 → T1 → T7b.
  ENTREGADO EN T7a: cuatro preferencias por usuario (formato de números
  es/internacional, formato de fechas relativa/absoluta, símbolo de moneda —solo
  el símbolo del costo de Datara, que es USD: SIN conversión— y comportamiento al
  abrir), migración 0006 (columnas nullable en user_settings), GET/PUT
  /api/settings con valores efectivos, card Preferencias en Perfil con botón
  Restablecer, formatters con preferencia y el formato inyectado en CADA llamada
  del chat (prompt principal, reparación, segunda pasada y post-procesador de
  números). Commits `a4d602d` + `610b1bc` + `8f91759`, pusheados a main.
  Migraciones: 0006 preferencias ✓ aplicada; T3 usará 0007, T2 0008 y T1 0009.
  PRÓXIMO: T3 (eliminar cuenta con gracia de 7 días cancelable).
  DECIDIDO POR EL MAINTAINER (16/10) — CÓMO SE LLEGA: presionando sobre el
  **nombre de usuario del sidebar** (abajo a la izquierda), que hoy es texto
  plano (`danieldelosriost@gmail.com`) con el botón "Log out" debajo. Es una
  **sección nueva**, no la card "Cuenta" del hub de Ajustes (los mockups de
  `Pantallas/settings/` quedan como referencia de contenido, no como ubicación).
  RESUELTO (19/10): el "Log out" del sidebar SE RETIRÓ y el cierre de sesión vive
  en la card Sesión del perfil (el mockup canónico del sidebar no tiene botón de
  logout, solo avatar + nombre + email).
  ORDEN DE TRABAJO (decisión del maintainer, 16/10): **profile primero**; el
  pulido de **login/registro** va DESPUÉS de profile.
  RELEVADO Y DECIDIDO (19/10, ver la sección Perfil de Fase 1.5): el backend NO
  tenía cambio de contraseña ni de correo (solo register/login/logout/me), y se
  agregó `POST /api/auth/password`; el correo queda SOLO LECTURA (sin verificación
  por mail, que exigiría infra de correo inexistente — **ACTUALIZADO EL 03/11: esa infra YA EXISTE y la verificación por mail quedó ENTREGADA (rama `feat/email-verification-recovery`, pendiente de merge), lo mismo que el nombre editable y todo el pulido de login/registro**); y el nombre NO se persiste
  todavía — se deriva del email (su campo entra en el pulido de login/registro).
  Antes de eso, el ROADMAP DE SETTINGS (post-B, "versión definitiva") queda así:
  (1) ✓ HECHO (16/10) — unificar Settings + wizard. Se eligió UNA sola pantalla
  con dos modos (Guiado / Avanzado) sobre un motor único de reglas
  (`web/src/routes/settings/useProviderSetup.ts`): flujo guiado de 3 pasos con el
  resultado del guardado como verificación, `/app/setup` redirigiendo por
  compatibilidad, aterrizaje de primer uso en Ajustes y una sola fuente de verdad
  para catálogo, gate de modelos y prellenado. La decisión salió de la Ronda 10
  de usabilidad (el maintainer eligió por comodidad, sin contar clicks) y esa
  misma prueba destapó el bug O10 —el modo se cambiaba solo a mitad del
  asistente al guardar el proveedor— arreglado el mismo día con test de
  regresión. Commits: `8c210f6` (motor, review nativa APROBADA) + `46b0f93`
  (fusión + las 3 formas probadas) + `d7e9b50` (arreglo + limpieza de las dos
  formas descartadas y del andamio `?variante=`). Suites: web 523, build ✓.
  (2) PÁGINA DE PERFIL → es el ítem de la próxima sesión, arrancando por la
  exploración inicial de arriba.
  (3) dashboard de uso/costos (`cost_usd`/tokens ya se guardan, no hay pantalla).
  (4) defaults de análisis (temperatura, prompt, límites de filas/plots).
  Ítem suelto: B5 — deuda de review/proceso (lineage de WU3 colgada en
  correction_required sin receipt + WU5 sin review por #4655):
  recuperar o abandonar a conciencia, no reanudar a ciegas.
  CORREGIDO EL 19/10 (el diagnóstico del 16/10 era incompleto y demasiado
  optimista): el review nativo NO está bloqueado "por el 9p" de forma
  determinística. La materialización de la vista del candidato (230 archivos /
  3,8 MB) es **INTERMITENTE**: medida con la forma real de la ruta da 15,1 s y
  20,5 s sobre 9p honda adentro del repo (vs 1,4–1,5 s en disco nativo), pero el
  19/10 un START entró igual en el presupuesto. El costo escala con la
  PROFUNDIDAD del camino — cada componente de directorio es un round trip de 9p
  —, no con el volumen. `gentle-ai` no tiene perilla para mover la raíz de las
  vistas ni para subir ese presupuesto (revisadas las 40 env vars y todas las
  flags de `review`), y un symlink en `.git/gentle-ai/candidate-views` se
  RECHAZA con `candidate-view-invalid` (probado apuntando afuera y adentro del
  repo: exige un directorio real). Evidencia publicada en
  `Gentleman-Programming/gentle-ai#4441` (comment 6271895494; los issues #4857,
  #4441 y #4557 ya cubren la familia, por eso se comentó en vez de duplicar).
  RECETA PARA LA PRÓXIMA VEZ: si un grupo de captura corre PARCIALMENTE (por
  ejemplo 3 de 4 lentes admitidas y el STATUS atado se pasa del presupuesto
  agregado, `retry_safe: false`), NO reintentar a ciegas: un solo STATUS de
  reconciliación devuelve el grupo residual REAL (quedó un slot) y capturarlo
  cierra el review.
  La SECCIÓN WIZARD quedó ✓ (nits cerrados 01/10, commits d42f53e/9853de3/8f1e284);
  queda el ítem NUEVO de generalizar las 3 preguntas sugeridas del wizard
  (opción B, sin LLM).

═══════════════════════════════════════════════════════
FASE 0 — CIMIENTOS  [✓ COMPLETA — VALIDADA RONDAS 1-4]
═══════════════════════════════════════════════════════
El loop núcleo del producto funciona y está probado:

✓ Loop PREGUNTA → RESPUESTA (SSE streaming: texto + tabla +
  gráfico + bloque de salida computado)
✓ Sandbox real: el resultado siempre es COMPUTADO, nunca
  inventado por el LLM (diferenciador central, objetivo #2)
✓ Trazabilidad: cada respuesta guarda el código que la generó
✓ Perfilado automático al importar (nulos, tipos, cardinalidad,
  muestras — objetivo #3 base)
✓ Sesiones persistidas en SQLite (retomar el trabajo, títulos
  automáticos, borrado limpio — objetivo #4 base)
✓ user_id desde el día uno + auth real con cookies (objetivo #5)
✓ API key POR USUARIO, nunca global pisable
✓ Proveedor LLM conectable (OpenAI-compatible: base_url + key
  configurables — funciona con OpenRouter hoy, objetivo #5)
✓ Correcciones de la auditoría del viejo Datara: async correcto,
  sandbox sin pickle (JSON end-to-end), figuras como plotly JSON,
  ejecución con límites de recursos e imports whitlisteado
✓ Robustez probada: 4 rondas de validación manual cerradas
  (R1-R8), 25 tests sandbox + 65 tests web + suite completa verde

═══════════════════════════════════════════════════════
FASE 1 — PULIR EL NÚCLEO  [✓ COMPLETA (15/09)]
═══════════════════════════════════════════════════════
Lo que la validación dejó señalado. Primera sesión de features.

✓ CINTURÓN (2/2) — COMPLETO Y ENTREGADO A MAIN (7 commits):
  1) Test de fitness de la frontera del store (la regla Supabase
     ya es ley, falla nombrando archivo y línea).
  2) BENCH DE REGRESIÓN DEL CHAT (scripts/bench.py, change SDD
     "chat-regression-bench" archivado): 10 preguntas canónicas
     contra config real de producción, ground-truth calculado en
     runtime, aserciones de errores+artefactos+números, costo
     estimado antes de gastar, reporte consola + .bench/last-run.json.
     Correr con: .venv/bin/python scripts/bench.py (opcional --limit N,
     --seed-experiment, --cache). Smoke test real cerró 3 bugs,
     entre ellos uno de PRODUCTO: el sandbox ahora permite clases.
  Pendiente de la Fase 1 además: el bug de orden del chat
  (respuesta arriba de la pregunta — diagnosticado, ver abajo).

✓ REALTIME / SESIONES EN VIVO — ENTREGADO, VALIDADO EN VIVO Y
  MERGEADO (05/09/2026): change SDD "realtime" completo (spec,
  22 escenarios; 3 PRs apilados ~2000 líneas, 2 con excepción
  de tamaño aprobada). EventBus por usuario con colas acotadas
  (drop + contador), SSE /api/sessions/events con cleanup en
  CancelledError, emisiones TITLED/STREAMING_STARTED/ENDED en
  el chat, frontend con reconexión por backoff jittered
  (4xx≠429 fatal, MAX_RETRIES=10) y React Query híbrido (patch
  optimista con cancelQueries + polling 10s de fallback).
  Validación en vivo de dos pestañas: LLM real por OpenRouter,
  punto verde apareciendo SOLO en la otra pestaña mientras
  stream-eaba la primera. La validación real cazó 2 bugs que
  340+ tests no vieron: STREAMING_ENDED faltante en el camino
  de error (indicadores colgados en otros tabs) y sidebar
  muerto cuando el fetch inicial falla — ambos arreglados con
  test de regresión (c3bb172, f52b76f). Prompt del chat guía
  al LLM a plotly-only (matplotlib bloqueado por diseño,
  169a6a9).
✓ Cancelar subida de archivos grandes (55e9308 — Ronda 5:
  cancel limpia, cero huérfanos verificados server-side)
✓ Reintentos de turnos (db89271 + mensaje 401 claro 1f31503 +
  Retry persistente dbf49e4 — Ronda 5, B en verde)
✓ DISEÑO VISUAL — ✓ CERRADO 15/09: identidad completa (design system
  "Dark Cockpit") + set de 18 pantallas canónicas en /Pantallas (6
  primarias, 3 estados, 5 del wizard, modal de tipado, 2 responsive, chat
  con gráfico, perfil). OJO: el diseño quedó DEFINIDO y APROBADO, no
  APLICADO — la app sigue con el estilo viejo. Ver "inventario de
  inconsistencias de diseño" en Transversal (quedó huérfano).
✓ SETTINGS WIZARD DE PROVEEDORES — ENTREGADO, VALIDADO EN VIVO
  Y MERGEADO (12-14/09/2026): change SDD "settings-provider-
  wizard". Backend WU1-4: migración 0002 (provider_type/
  base_url con preservación total), guardado relajado
  (cualquier modelo se guarda; la whitelist se MUEVE al chat —
  422 model_not_allowed antes de persistir el turno), guard
  SSRF (https + host público; loopback exento SOLO ollama/
  lmstudio; resuelve DNS y bloquea rangos privados), registry
  + POST /api/settings/models siempre-200 con adaptadores por
  proveedor (ollama vía /api/tags). Wizard UI WU5+6: 5 pasos
  (Proveedor / Credenciales / Modelo / Prueba de conexión /
  Listo), presets OpenRouter/Ollama/LM Studio/Groq/Custom,
  listado en vivo con texto libre de fallback, prueba de
  conexión costo-cero (sin llamada LLM), re-entrada prellenada.
  PRs #6-#13 squash-mergeados (main @ c273062) + buscador de
  modelos en el paso Modelo (6af03c0). Ronda 8 A-G verde (F1
  proveedor local diferido — sin proveedor instalado; receta
  en el checklist). Los adaptadores nativos van en Fase 4.
✓ RIGOR DE RESPUESTAS — ✓ MOVIMIENTOS 1-2 ENTREGADOS Y VALIDADOS
  (Ronda 6, 08/09): row_count autoritativo + disciplina de
  citación (be704a9); bench corre el PROMPT REAL (25cdca5);
  intent routing + segunda pasada grounded PERSISTIDA (f8fa796);
  narrativa con valores EXACTOS de la tabla (9038ce3). pytest
  357/357, bench Q1-Q11 11/11. Veredicto del usuario: respuesta
  de analista nivel Claude/Gemini.
◐ Nits del backlog: los pendientes migran a FASE 1.5 (pulido
  por sección); mismos ya hechos: mismo-nombre 409 (fb15556),
  sweep de uploads al borrar sesión (6a0e31b).
useMessages + tiebreaker id en la SQL. (Confirmado visualmente
  en el navegador por el usuario — 05/09/2026.)

✓ WIZARD FIRST-RUN — ✓ MOVIMIENTO 3 ENTREGADO, VALIDADO EN VIVO Y
  MERGEADO (11/09/2026): change SDD "mov3-ui-wizard" completo
  (spec 16 escenarios, design 8 decisiones, 11 tareas). Overlay
  en AppShell: triggerHolds reactivo (0 sesiones Y 0 archivos,
  queries resueltas, no streaming, no descartado), auto-open +
  latch un-engaged, 4 pasos (Welcome → Upload con sesión auto →
  pregunta sugerida → Finish con input poblado sin enviar),
  skippable con localStorage, reabrible desde el empty state del
  chat, affordance de sesión inline en FilesView. PRs #4/#5
  mergeados (4e71653, c9e25e3); branches eliminados. Verify
  inline cazó 1 CRITICAL (remediado, 2623f6d). Ronda 7 A/B/C
  verde; fix cazado en vivo: Get started no avanzaba de paso
  (d5653bf). La pregunta sugerida corre el pipeline RIGOR igual
  que cualquier mensaje.

═══════════════════════════════════════════════════════
FASE 1.5 — PULIDO POR SECCIÓN (QoL)  [NUEVA — ACORDADA 11/09]
═══════════════════════════════════════════════════════
Recorrer cada sección con lupa (Chat, Files, Wizard, Archives,
Settings, Login) y pulirla al máximo con features de calidad de vida
pensadas por sección. Entra DESPUÉS de cerrar Fase 1 (diseño
visual + settings wizard de proveedores) y ANTES de Fase 2.
Scope sembrado del backlog (11/09 + 14/09):

Chat — triage de pulido 15/09 (verificado en código, orden
aprobado por el usuario; arranca la Fase 1.5):
✓ 1. Botón DETENER turno en curso (48ff038, 15/09 — validado
  en vivo por el usuario): botón exclusivo Detener/Send +
  abort en unmount/cambio de sesión + run_code mata el
  subprocess al cancelar + abort silencioso en la ventana
  pre-headers (fix del verifier). Nit pendiente: el Retry
  tarda en aparecer porque espera el refetch del historial
✓ 2. Code blocks + copiar (933c7d7, 15/09 — validado en vivo:
  header Python + Copiar/Copiado/Error, gating code no vacío,
  sin dependencias nuevas). Descubierto en la validación: el
  composer está en ENGLISH ("Ask a question about your data...",
  "Send") — auditar TODA la copy user-facing al español neutro
✓ 3. Paginación de historial (8a1683e, 15/09 — validada en
  vivo con variante de página=10 + hard reload): cursor keyset
  (before), botón "Cargar mensajes anteriores", scroll
  preservado (pin liberado + compensación por delta), demote-
  then-refetch para que el refetch post-turno no deje huecos.
  Suite de integración live-modeled (ChatPagination.test).
  Nota validación: la tab SPA corriendo bundle viejo simula
  "no aparece el botón" — nit Cache-Control sembrado
✓ 4. Descargas: gráfico → PNG (plotly.toImage scale 2, guard
  de doble click) + tabla visible → CSV (buildCsv puro: RFC 4180
  + BOM UTF-8 + respeta el sort activo). VALIDADO EN VIVO y
  pusheado 16/09 (d963f3d, con tests por botón). PNG impecable.
  CSV: Excel del usuario no separa columnas (su Windows tiene
  sList=';') — DECISIÓN 16/09: coma estándar RFC 4180, variante
  ';' queda como nit opcional. CSV del dataset COMPLETO sigue
  aparte (decisión de diseño pendiente). Nit: reubicar el botón
  PNG (queda arriba de la imagen, confunde)
✓ 5. Renombrar sesión manualmente (86963d8, 16/09 — validado
  en vivo): PATCH /api/sessions/{id} (trim, vacío→422
  invalid_title, >200→422, ownership→404) + store
  rename_chat_session + evento SSE reutilizando TITLED
  (persist-then-emit, cero cambios en el handler del sidebar)
  + editor inline (✎ → Guardar/Cancelar, Enter/Escape).
  Nit: el error del rename queda silencioso → surfear en UI
✓ 6. Costo/tokens visible (5446a93, 16/09 — validado en vivo):
  MessageResponse expone tokens_in/tokens_out/cost_usd (ya se
  persistían desde Fase 1; solo faltaba exponer) + línea meta
  en la burbuja del asistente ("1.819 tokens · US$ 5,5200",
  null-safe: mensajes viejos sin datos no muestran nada).
  Costo = estimado con price map estático (fallback gpt-4o para
  modelos desconocidos). Queda abierto: acumulado por sesión
✓ 7. Tokens de diseño (6ef299a, 16/09 — validado en vivo, cero
  cambio visual): web/src/design/tokens.ts tipado (colors light
  + dark code block, spacing, typography, radii) + ChatMessage
  consume tokens + test que fija valores exactos como recibo.
  La capa queda de base para el rediseño; inventario de
  inconsistencias entre componentes en Transversal
✗ Banner de API key fallida → apuntar explícito a Settings
  ("configure your API key in Settings and retry") + Retry
◐ ROBUSTEZ — OBRA EN CURSO POR SDD (16/09, definida con el
  usuario; aspiración: CERO banners en rojo salvo errores
  legítimos — apikey inválida, sin créditos, modelo que no da
  la talla). Jugadas: (1) repair loop de runtime_error →
  traceback al modelo, 1 intento; (2) retry del envelope JSON
  CON feedback del error (hoy reintenta mismo-prompt); (3)
  whitelist DATARA_ALLOWED_MODELS guiada por bench con umbral
  mínimo (la inadequación se decide al configurar, no en
  runtime); (4) banners tipados que separen sandbox vs LLM vs
  auth (hoy se ven igual en rojo crudo). Repros conocidos: 3
  preguntas con z-ai/glm-5.3-flash fallan determinista;
  NameError df_result (misma clase robustez). Estrenada por SDD
  formal (change chat-robustez): planificación completa +
  slice 1/5 implementado — ver REGISTRO DE HITOS.
✓ Sandbox locale: ARREGLADO 16/09 (4cc9046) — build_system_prompt
  declara "locale restriction" (solo C/POSIX, nunca setlocale,
  mapear nombres con dict propio) + assertion de regresión en
  test_hardening. Validado: el repro "monto promedio por día"
  ahora grafica con días en español sin crash. Nota: las
  guardias de prompt son BLANDAS (aplican a todo modelo, no
  garantizan — la garantía viene de la obra ROBUSTEZ)

  Nits de chat descubiertos en validaciones 16/09 (pendientes):
  ✗ Botón "Descargar PNG" arriba de la imagen — reubicar
  ✗ Toggle mostrar/ocultar del bloque de código
  ✗ Error del rename silencioso (sin banner ni revert en UI)
  ✗ Variante CSV Excel con ';' (solo si el doble-clic importa)
  ✗ AGENTS.md stale: dice "~357 backend / ~88 web"; al 19/10 van 752 / 546

Files — triado 24/09 (inventario verificado contra el código;
orden por importancia, un ítem prioritario por sesión):
Backend hoy: POST/GET /api/sessions/{id}/files, GET /api/files,
GET /api/files/{id}/profile, DELETE /api/files/{id}. Formatos
.csv/.tsv/.xlsx/.json. Dedupe por nombre por sesión (409).
Perfil stats + sample. Delete duro con cascada de profiles.

TIER 0 — SEGURIDAD (crítico; resolver primero)
✓ F1. Límite de tamaño server-side + cuota + tope de expansión —
  HECHO, VALIDADO EN VIVO Y PUSHEADO (0b70605, 24/09). Cap
  por-archivo con lectura en chunks (nunca más read() entero a
  RAM) + fast-reject por Content-Length; guard PRE-PARSE del XLSX
  (inspecciona el tamaño descomprimido declarado del zip ANTES de
  openpyxl → corta el zip-bomb) + backstop post-parse de
  footprint; cuotas por sesión/usuario contra la tabla files.
  Topes por env: DATARA_MAX_UPLOAD_BYTES=100MB ·
  DATARA_MAX_EXPANDED_BYTES=500MB · DATARA_MAX_SESSION_BYTES=1GB ·
  DATARA_MAX_USER_BYTES=5GB. Archivos: server/limits.py (nuevo),
  server/api/routers/files.py, core/data/parser.py,
  server/services/sqlite_store.py + 8 tests nuevos (suite 598/598).
  RESIDUAL CONOCIDO (documentado, no bloqueante): Starlette
  parsea y spollea el multipart a un archivo temporal ANTES de
  que corra el handler, y TAMBIÉN antes del chequeo de auth
  (verificado en fastapi/routing.py:430 request.form() vs :481
  solve_dependencies) → un body gigante todavía llega a /tmp
  antes del rechazo, incluso sin estar logueado. Starlette NO
  tiene tope para file parts (formparsers.py:183: el 1MB de
  max_part_size solo aplica a campos de formulario; spool_max_size
  1MB = por debajo queda en RAM). El server escucha en 127.0.0.1
  → riesgo BAJO hoy, real al exponerlo (hosted Fase 5 o --host
  0.0.0.0).
✓ F1.1. Guard de body acotado al upload (POST
  /api/sessions/{id}/files) — HECHO, VALIDADO EN VIVO Y PUSHEADO
  (1a093df, 24/09 sesión 7). Middleware ASGI puro
  (server/api/upload_guard.py: UploadSizeGuard + install_upload_guard)
  que corre ANTES del parseo del multipart: 413 si el Content-Length
  declarado supera DATARA_MAX_UPLOAD_BYTES + margen de 1MB, 411 si
  falta Content-Length (variante elegida por el usuario: cierra el
  bypass chunked; el SPA y curl siempre lo mandan), 400 si viene
  malformado. Registrado en main.py ANTES de CORS (CORS queda
  outermost y sus headers aplican al 413/411). Margen y mensaje
  COMPARTIDOS con el fallback del handler (files.py) para que no
  diverjan; el check inline queda como defensa-en-profundidad. Cierra
  el residual de F1: el camino NO autenticado ya NO escribe en /tmp
  (antes el body se spolleaba y recién después daba 401).
  OJO al justificarlo: acotarlo a la ruta NO es "caparía el SSE"
  (el SSE es un GET sin body) sino precisión de política + mensaje
  específico del límite por archivo. Archivos: server/api/upload_guard.py
  (nuevo), server/api/main.py, server/api/routers/files.py,
  tests/integration/files/test_upload_limits.py (TestBodyGuard: 413
  no-auth sin tocar disco + 411 vía harness ASGI determinista),
  tests/integration/files/test_files_api.py. En vivo: 2MB no-auth →
  413 exacto, chunked → 411, cero archivos en disco.

TIER 1 — INTEGRIDAD DE DATOS (bugs reales)
✓ F2. UNIQUE (user_id, chat_session, filename) + IntegrityError→409 —
  HECHO, VALIDADO EN VIVO Y PUSHEADO (1d5acf7, 24/09 sesión 6).
  Antes: el dedupe por nombre era SELECT + INSERT sin constraint
  (0001_init.sql:42-55) → race TOCTOU: dos uploads concurrentes
  del mismo nombre creaban 2 filas apuntando al MISMO storage_path;
  borrar una hacía unlink del archivo compartido y rompía la otra.
  Archivos: server/migrations/0003_files_unique_name.sql (nuevo),
  server/api/routers/files.py, server/services/sqlite_store.py,
  tests/unit/auth/test_sqlite_store.py, tests/integration/files/*.
  OJO: los fixtures de los tests de files aplicaban SOLO
  0001_init.sql → el constraint habría quedado sin testear; ahora
  aplican todas las migraciones.
✓ F3. Excel multi-hoja — CERRADO Y PUSHEADO (5fa1024, 25/09).
  Antes se perfilaba solo la PRIMERA hoja sin avisar
  (parse_upload_sheet existía sin usar). Ahora: picker de hoja en
  la UI, endpoint de selección, aviso de hojas extra, y el sandbox
  lee la hoja ELEGIDA (chat_context emite sheet_name + el prompt
  agrega un bloque condicional xlsx-only con
  pd.read_excel(sheet_name=...)). Reprofila la hoja activa;
  rollback atómico files+profiles. focused 112, backend 618,
  web 290, bench 11/11.

TIER 2 — UX ALTO IMPACTO / BAJO ESFUERZO
✓ F4. Confirmación antes del delete — CERRADO Y PUSHEADO
  (f8fbfa6, 25/09). Nuevo ConfirmDialog (diálogo que nombra el
  archivo; Cancel/Escape no borran; el trigger queda deshabilitado
  mientras la request vuela). Undo/papelera NO se hizo (declinado
  por diseño al agregar infra nueva). 4 archivos +330/-2; web 302.
✓ F5. Abort del upload del wizard — CERRADO Y PUSHEADO
  (796423b + 0641402, 25/09). WizardOverlay ahora es dueño de
  uploadAbortRef (unmount + skip) y lo pasa a UploadStep por
  abortRef; el hijo escribe el controller por-upload, lo limpia en
  finally y gatea la dropzone mientras está pending. Cubre también
  salir durante la creación de sesión. 5 archivos; web 307.
✓ F6. Mismatch .tab — CERRADO Y PUSHEADO (6b31b08, 25/09).
  Alineada la UI al server: nueva fuente única
  web/src/lib/uploadFormats.ts (sin .tab), las dos dropzones +
  ChatView consumen de ahí. Invariante testeada contra la
  allow-list del server. 7 archivos +102/-19; web 314.
✓ F7. Tipo del cliente alineado — CERRADO Y PUSHEADO (49c1982,
  25/09). profile_summary ficticio eliminado; TODOS los tipos de
  respuesta de files/profile alineados con sus modelos Pydantic
  reales, con pins de tipo set-exactos. 3 archivos +104/-15;
  web 316.

TIER 3 — CALIDAD / CORRECTNESS
✓ F8. Perfilado offloaded — CERRADO Y PUSHEADO (f5d3bfe, 28/09).
  Los call-sites pandas CPU-bound del router de files ahora van por
  await asyncio.to_thread(...) con dos helpers sync de módulo; los
  tests prueban el offload por identidad de thread. 2 archivos;
  suite backend 632.
✓ F9. Vista de perfil tabulada — CERRADO Y PUSHEADO (c86b519,
  28/09). Nuevo ProfileTable.tsx: <table> real (Columna | Tipo |
  Nulos | Únicos | Mín | Máx) desde schema.columns + stats, con el
  JSON crudo preservado colapsado en <details>. 4 archivos
  +242/-5; web 329.
✓ F10. Paginación con cursor — CERRADO Y PUSHEADO (2613f08 +
  86d7bae, 29/09). Keyset (before/id) en GET /api/files y en el
  listado por sesión, espejo del historial de chat: store
  limit/before_id keyword-only default unlimited (chat_context y
  archive siguen pidiendo la lista completa); routes clamp 1..200
  (default 50); useFilesGlobal → useInfiniteQuery + botón "Cargar
  más" (página 50 + 3, cero solapamiento, validado en vivo).
  2 work units: backend 4 archivos +302/-27, frontend 6 +278/-30.

TIER 4 — CONVENIENCIA
✓ F11. Re-descarga del archivo original — CERRADO Y PUSHEADO
  (09da35f backend + 7d26899 frontend, 29/09). GET
  /api/files/{file_id}/download: ownership con get_file(id, user_id)
  (ajeno / inexistente / ausente en disco = el MISMO 404, sin filtrar
  existencia), contención contra UPLOADS_DIR antes de tocar el disco,
  Content-Disposition con el nombre original (Starlette, RFC 5987
  para acentos) y Content-Type derivado del format. Acción "Descargar"
  por fila en la columna Actions de la tabla de Files (anchor plano,
  sin blob ni api.ts). 5 archivos +386; backend 642, web 332, build ✓.
  Revisión RDD nativa intentada (lineage review-7b68f128682d65aa,
  consent granted) → reviewer rechazado x2 por el defecto de transport
  → unachievable + terminal operation_timeout; fallback RDD-off medium
  PASS WITH FINDINGS (el verificador falsó por regresión inyectada:
  sacar ownership / contención / existencia hace fallar el test
  correspondiente); verificación end-to-end por HTTP (bytes idénticos,
  headers correctos, 404 ajeno, 401 sin cookie) + validación EN VIVO
  del usuario OK. Follow-ups anotados: 500 en vez de 404 si una fila
  corrupta apunta a un directorio (no alcanzable por upload); tests de
  media type faltantes para tsv/json/octet-stream.
✓ F12. Rename de archivo — CERRADO Y PUSHEADO (605c71f backend +
  206de3f frontend). PATCH /api/files/{file_id}: ownership (ajeno /
  inexistente = el MISMO 404), 422 con {code: invalid_filename} para
  vacío, >255, separadores de ruta, caracteres de control y cambio de
  extensión (regla elegida por el usuario: el format se deriva de la
  extensión AL SUBIR y se desincronizaría), 409 con el MISMO texto
  compartido del upload, y no-op 200 al renombrar a su propio nombre.
  El disco no se toca: storage_path conserva el basename subido y solo
  cambian el nombre visible y el Content-Disposition de la descarga.
  UI: "Renombrar" en la columna Actions con editor inline en la celda
  del nombre (Guardar/Cancelar) y error inline con el detalle del
  backend. Backend 665, web 339, build ✓. Revisión RDD nativa: consent
  RELADO y el usuario eligió "Saltear esta vez" → decline
  candidate-scoped validado (sin registro de review, no es el kill
  switch) → assess medium → verificador independiente PASS WITH
  FINDINGS (sin BLOCKER/CRITICAL) que además cazó 3 tests que no
  discriminaban; corrección de F7/F2/F3/F1 probada por regresión
  inyectada. E2E por HTTP real 14/14 + validación EN VIVO OK.
✓ F12.1. Unicidad case-insensitive (follow-up cazado por la validación
  EN VIVO del usuario) — PUSHEADO (6615a43 + 605c71f). El usuario
  encontró que UNA mayúscula esquivaba la regla de duplicados
  (ventas.csv vs Ventas.csv): agujero PREVIO, también en el upload
  (reproducido: upload CASE.csv y case.csv → 201 los dos). Arreglado en
  las dos capas: get_file_by_name pliega con str.casefold (Unicode —
  AÑO.csv choca con año.csv, cosa que NOCASE no puede) y la migración
  0004 recrea idx_files_unique_name con COLLATE NOCASE; el guard
  RENOMBRA al perdedor en vez de borrarlo (case.csv →
  "case.csv (dup-175)") y se ejercitó sobre la DB real sin perder
  filas. El 409 ahora nombra el nombre que EXISTE, no el tipeado.
  Migraciones 11, Files 106, backend 672, build ✓; los 4 tests nuevos
  probados por inyección. E2E del fix 9/9.
  Follow-ups anotados: has_profile=false en la respuesta del PATCH (sin
  consumidor), sin test a nivel hook de useRenameFile, estados de borde
  del editor (Escape / re-click) sin test.
✓ F13. Nits de tablas CERRADO Y PUSHEADO (314bb2c backend + a06d554
  frontend). (1) La tabla de resultado con 0 filas mostraba solo el
  encabezado → ahora renderiza "Sin resultados" en el cuerpo (guarda de
  colSpan para 0 columnas). (2) df_result con >20 filas recortaba a
  head(20) sin aviso → el sandbox reporta total_rows (largo REAL del
  frame) y la UI muestra "Mostrando las primeras 20 de N filas."
  (artefactos viejos sin el campo: sin aviso). (3) Números crudos en
  tablas → formateador ES determinístico y sin ICU (formatNumbers.ts:
  punto de miles + coma decimal, ≤6 decimales, ceros finales fuera,
  -0→0) aplicado a la tabla de resultado, la de perfil (F9, que usaba
  en-US) y la lista de Files (Rows/Size); orden y export CSV siguen con
  los valores crudos. Decisión del usuario: español en TODAS las tablas.
  Backend 674, web 354, build ✓. RDD nativo: el usuario eligió "Saltear
  esta vez" (decline candidate-scoped, sin registro); assess high (13
  paths/268 líneas) + verificador independiente read-only PASS WITH
  FINDINGS (sin BLOCKER/CRITICAL; follow-ups: |v|≥1e21 cae a notación
  exponencial — preexistente e inalcanzable; tests de "CSV crudo", empty
  con columns:[] y string numérico sin discriminar). Validación EN VIVO
  OK: los 3 nits confirmados en el browser.

✓ F14. Lista de Files por sesión — CERRADO 29/09 (sesión 15; commit
  2e28f08 pusheado a main). Decisión de producto (sesión 15): opción B —
  lista global + filtro de vista con default "Solo esta sesión" y opción
  "Todas las sesiones" para no perder la gestión cross-sesión. El hook
  dormido useFiles(sessionId) pasó a paginado por cursor compartiendo un
  único motor con useFilesGlobal() (que queda intacto, igual que el trigger
  del wizard en AppShell); un solo activeList maneja empty state, paginación
  y error por vista. 5 archivos +514/-255; focused 79, web 365, build ✓;
  validación EN VIVO del usuario OK. La revisión RDD nativa volvió a fallar
  por el defecto #4030 (6ª+ reproducción acá, mismo string de 2.5.0 a 3.7.0):
  el usuario autorizó reportarlo → 1 ocurrencia en #4030
  (issuecomment-5900744641); decline candidate-scoped + fallback RDD-off
  medium + verificador independiente read-only PASS WITH FINDINGS (0
  BLOCKER/CRITICAL; findings follow-up: falta test del criterio 4,
  contract.test.ts tautológico, cursor por id heredado de F10, "—"
  transitorio en la columna Session).
  PROBLEMA ORIGINAL (reportado por el usuario, sesión 14): la
  tabla de Files es GLOBAL (`useFilesGlobal` → GET /api/files, todos los
  archivos de todas las sesiones) y cambiar "Upload to session" solo
  cambia el DESTINO del upload, no la lista → al cambiar de sesión se
  siguen viendo TODOS los archivos, lo que hace pensar que la sesión ya
  tiene archivos cargados cuando en realidad puede no tener ninguno.
  "Tiempo real" = que la lista reaccione al cambio de sesión (no live
  updates). Ya EXISTE `useFiles(sessionId)` → GET
  /api/sessions/{id}/files, sin consumidor desde F10/F11.
  Decisión de producto PENDIENTE — elegir UNA:
  (A) Solo la sesión elegida: la tabla lista únicamente los archivos de
      la sesión seleccionada (el selector maneja vista + destino);
      empty state "No hay archivos en esta sesión."; se pierde la vista
      global cross-sesión.
  (B) Global + filtro "Todas las sesiones" / "Solo esta sesión" (default
      Todas): conserva la gestión cross-sesión y quita la confusión al
      filtrar. Un control más en la página.
  (C) Global agrupada por sesión (encabezados por sesión) resaltando la
      elegida: no cambia el modelo de datos, pero es más sutil.
  OJO al implementar: `AppShell` también usa `useFilesGlobal()` como
  disparador del wizard — el consumidor a tocar es `FilesView`; revisar
  ese trigger antes de cambiar el hook. Paginación por cursor (F10) y
  tests existentes (FilesView.test.tsx) quedan a actualizar.

Notas transversales: sin dedupe por hash de contenido (solo
nombre); encoding/sheet_name no aparecen en los listados. El
cruce multi-dataset (Fase 2) queda FUERA del pulido de Files.

Wizard:
✓ Gate "session-creation pending" explícito en triggerHolds — CERRADO
  01/10 (sesión 16; commit d42f53e). useCreateSession registra mutationKey
  ["createSession"] y AppShell gatea triggerHolds con useIsMutating
  (react-query v5: el estado de mutación es por-instancia, no compartido).
✓ setEngaged al soltar archivo (design D3) — CERRADO 01/10 (9853de3):
  UploadStep.onDrop engancha el latch sincrónicamente antes del primer await.
✓ Test runtime de keys inertes tras rollback — CERRADO 01/10 (8f1e284):
  wizardRollbackInert.test.tsx (payloads foráneos → defaults seguros;
  arranque en frío con la key presente no rompe nada).
✓ Sugerencias del paso Question derivadas del perfilado — CERRADO 01/10
  (sesión 17; 2af95f4 "feat(wizard): derive suggested questions from the
  dataset profile" + 4db7317 "fix(chat): re-apply wizard suggested questions
  on reuse"). `buildSuggestions(profile)` es pura y determinista (dtype +
  cardinalidad, SIN LLM) con fallbacks genéricos; el fileId se threadea
  Upload → WizardOverlay → QuestionStep. El fix de reuse lo cazó el
  maintainer en validación EN VIVO (el latch one-shot nunca se reseteaba).
  Al elegir una sugerencia SOLO se precarga el composer; el pipeline RIGOR
  corre normal al enviar.

Settings wizard (sembrado 14/09, Ronda 8):
✗ Paso Credenciales con Ollama/LM Studio queda vacío (solo
  el título, parece roto) — texto informativo ("no se
  requiere clave") o saltar directo a Modelo
✗ Banner model_not_allowed muestra el detalle crudo — pulir
  el copy (el rechazo 422 en sí ya está validado)
✗ Nits WU4: propagación de OPENAI_TIMEOUT, comentarios
  viejos en chat.py, DRY en _resolve_model

Login:
✗ Pulir login/registro (diseño visual ya definido en Fase 1 —
  Dark Cockpit; pulir validación, copy y estados de error). ORDEN
  DECIDIDO: va DESPUÉS del perfil. Incluye el campo de NOMBRE, anotado
  el 19/10 al cerrar la primera entrega del perfil: hoy el nombre
  mostrado se DERIVA del email (helper displayNameFromEmail) porque la
  tabla users no tiene columna de nombre; el registro debería pedirlo.
  ACTUALIZADO 19/10 (sesión 23): hacerlo editable en el PERFIL ya está decidido
  y es la obra T1 de `odd/tasks/profile-roadmap.md` (la última del orden por
  complejidad, porque es la más chica); queda por decidir si además el registro
  lo pide al crear la cuenta.

Perfil:
◐ SECCIÓN PERFIL — PRIMERA ENTREGA ✓ (19/10, sesión 22) + FUNCIONES ✓
  DECIDIDAS (19/10, sesión 23). Entregado y validado EN VIVO: /app/profile con card Cuenta
  (email SOLO LECTURA + cambio de contraseña que CIERRA LAS DEMÁS
  SESIONES dejando la actual) y card Sesión (cerrar sesión); se entra
  desde el bloque de usuario del sidebar, que ahora tiene avatar +
  nombre derivado del email y perdió el botón "Log out". main @
  711cf2a (`7f8b635` backend + `711cf2a` frontend); ficha
  odd/tasks/profile-section.md. El mockup Pantallas/settings/perfil.txt
  dio ESTRUCTURA Y COPY (no sus colores: la app no está repintada).
  ORDEN VIGENTE (reordenado 26/10, sesión 24): **T7a ✓ preferencias, ENTREGADA**
  → T3 (eliminar cuenta con gracia de 7 días, migración 0007) → T2 (sesiones
  activas + aviso in-app, 0008) → T6 (bitácora personal) → T5 (export de la
  cuenta) → T4 (panel de consumo) → T1 (nombre editable, 0009) → **T7b** (repintado
  Dark Cockpit, ÚLTIMO: el maintainer priorizó funcionalidad primero). Ficha:
  `odd/tasks/profile-roadmap.md` (+ `odd/tasks/profile-preferences.md`).

Settings hub (triage 15/09 — propuesta Claude + filtro MVP) [SUPERSEDIDO:
  el plan `odd/tasks/settings-production-readiness.md` reemplazó a este
  triage y ya se cerró (WU1-WU5 + B1-B6 + la fusión, main @ 642fbe5). Los ✗
  de abajo se conservan como REGISTRO de lo que quedó fuera de ese plan —
  NO son pendientes activos del hub.]
Triage original:
✗ Ajustes pasa de pantalla única a hub con tabs: Cuenta · IA y
  modelo · Datos y privacidad · Preferencias (notificaciones
  absorbidas en Preferencias). Perfil = tab "Cuenta" — **ANULADO**: el
  16/10 se decidió que Perfil es una SECCIÓN NUEVA (y el 19/10 se entregó
  en /app/profile), así que ese "Ajustes activo" del mockup es residuo
  viejo de la decisión del 15/09.
✗ AHORA (barato y real): IA y modelo — selector de modelo
  default editable sin rehacer el wizard + nivel de detalle de
  respuesta (conciso/explicativo) + idioma (los 3 viajan en
  cada system prompt, regla una-por-llamada); Preferencias —
  formato números/fechas (hoy hardcode: ≤6 decimales +
  separadores de miles), moneda default, comportamiento al abrir
✗ PRÓXIMO (backend moderado): Datos y privacidad — retención de
  archivos subidos + "borrar todos los datasets" (decisión real
  para quien sube CSVs de negocio; se pregunta antes de subir)
✗ DESPUÉS: sesiones activas con revocación remota (hoy sesiones
  simples en SQLite); notificaciones in-app (evento done +
  Notification API del navegador)
✗ CORTADO/APARCADO: Plan y uso (no hay planes ni billing — el
  usuario paga con su propia key de proveedor, Ronda 8; si
  acaso, panel de uso informativo local), 2FA (infra TOTP +
  recuperación para una beta sin usuarios reales), notificaciones
  por email + resumen semanal (subsistema entero; el análisis ya
  streamea en vivo en la pestaña abierta)

Settings — auditoría y plan de producción (05/10/2026):
El card `odd/tasks/settings-production-readiness.md` (engram `audit/settings-section`,
obs #507) REEMPLAZA al triage de arriba como plan de trabajo de la sección. Hallazgos
verificados contra el código:
(P1 ESTRUCTURAL) Settings es un SUBCONJUNTO de Setup: SettingsView solo edita
  api_key + default_model (SettingsView.tsx:6-9,40-45); provider_type/base_url viven
  en el wizard, y para cambiar una URL custom hay que recorrer los 5 pasos y pasar la
  prueba de conexión (Setup.tsx:422 la exige para habilitar Finalizar). Ojo: base_url
  solo es editable en el wizard para el preset custom (Setup.tsx:222-236).
(P2) SettingsView NO verifica la key al guardar: dice "Settings saved" sin probar
  nada. El wizard sí prueba (probe /models, costo cero, Setup.tsx:341-378). Sí hay
  recuperación: auth/invalid_key → banner "Ir a Ajustes" (errorCodes.ts:100-102).
(P3) El footgun del modelo no permitido nace en el WIZARD (lista viva sin filtrar,
  provider_registry.py:213) que guarda cualquier modelo; PUT /api/settings NO valida
  whitelist (settings.py:141-145); el rechazo es en CHAT (chat.py:429-437) y el
  frontend lo mapea a un warning "Modelo no disponible" con action "none" — SIN botón
  (errorCodes.ts:109-111 + sse.ts:73-78). La whitelist además alimenta el pricing
  (main.py:137). Corrección de un diagnóstico previo: el dropdown de Settings NO deja
  elegir un modelo rechazado (sale de la whitelist misma).
(P4) Idioma: SettingsView en inglés, Setup/copy en español.
(P5) Sin capa para no-técnicos.
Mockups objetivo ya existen: Pantallas/settings/ajustes.txt (hub Ajustes: card
"Proveedor de LLM" + "Cuenta") y perfil.txt (cuenta) — SettingsView no implementa
ninguno.
Plan: WU1 unificar Settings/Setup; WU2 test de conexión al guardar; WU3 whitelist +
acción al banner model_not_allowed; WU4 copy español; WU5 capa "a prueba de tontos"
(modelos recomendados pago/gratis, links directos al proveedor para API key y
créditos, guías paso a paso) — bloqueada por PD1-PD4. NO es SDD: ODD, un ítem por
sesión, sin riesgo de seguridad activo (key Fernet + SSRF guard sanos, sin F1/F2).

✓ SECCIÓN CERRADA (15/10/2026 — main @ c1c2037). Los 5 work units + el backlog
post-WU5 (B1-B6) quedaron implementados, verificados, validados EN VIVO por el
maintainer y pusheados. **16/10: se le sumó la FUSIÓN del wizard con Ajustes**
(punto (1) del roadmap de abajo): una sola pantalla con dos modos sobre un motor
único, el bug O10 arreglado con test de regresión, y las dos formas descartadas
de la Ronda 10 borradas con su andamio — main @ 642fbe5 (PR #21), suites web 523
y build ✓. Resumen por ítem (detalle, evidencia y tests en el card):
WU1 ✓ hub editable (7ccd1cc) — provider_type/base_url/api_key editables desde
  Ajustes sin recorrer el wizard; base_url read-only en presets nombrados, con
  "Editar URL"/"Usar predeterminada" para no pisarla. Review nativo APROBADO.
WU2 ✓ guardar-y-verificar (db2b9f4) — "Guardado · Conectado" o "Guardé, pero
  falló la conexión: …"; antes decía "saved" sin probar nada. APROBADO.
WU3 ✓ desync de whitelist (08f54d4) — el wizard ofrece solo modelos permitidos
  (intersección con la lista viva del proveedor) + guard en submit; el banner
  model_not_allowed ahora lleva a Ajustes. Review llegó a correction_required
  (halló un CRÍTICO real: whitelist vacía = dead-end de setup) → corregido con
  test; el validator falló por transport y el STATUS atado flakeó → lineage SIN
  receipt. → candidato sin review terminal.
WU4 ✓ copy de SettingsView a español neutro (2b6c6bf), alineado a Setup/copy y al
  mockup ajustes.txt. APROBADO.
WU5 ✓ capa "a prueba de tontos" (496d60e) — catálogo OpenRouter (8 modelos,
  pago/gratis con precios), guías paso a paso + links directos, y presets no
  OpenRouter en "Próximamente" (por el dead-end D6). Review NO completó: #4655
  (STATUS atado, operation_timeout 3/3) → candidato SIN review, ocurrencia
  reportada en el issue.
B1 ✓ GATE PROVIDER-AWARE (D6) (e56e0aa) — la whitelist curada deja de aplicarse a
  Groq/Ollama/LM Studio/Custom; solo OpenRouter y el fallback de entorno siguen
  gateados. Cierra el dead-end que dejó WU5 y habilita los 5 presets. Review
  nativo APROBADO (`review-77efa93813d92957`) con 3 advisories → B6.
B2 ✓ catálogo + guías más allá de OpenRouter (0d094b8) — 3 modelos Groq reales
  con tarifa verificada, guías por proveedor, catálogo/guía keyed al provider y
  facilitación del paso Modelo (placeholder por proveedor, "Reintentar", dedupe
  de avisos, hint local). Review nativo APROBADO con 3 advisories.
B2-advisories ✓ pricing provider-aware (39aa921) — `_PROVIDER_SCOPED_RATES` con
  clave (provider, slug): un slug de Groq ya no se pricea a tarifa Groq bajo otro
  proveedor (desconocido → NULL, nunca un número equivocado); priceLabel con
  hasta 3 decimales ($0.075). Sesión de mantenimiento: 27 lineages huérfanas del
  store de review abandonadas → `clean`.
B3 ✓ hardening del probe (8325eab) — `AbortController` + timeout de 15s en el
  cliente para que el botón no quede clavado en "Comprobando…" (el server ya
  acotaba a 5s: el hueco era el abort del cliente). Verificación independiente
  pass_with_advisories.
B4 ✓ pulido chico (b0940a6 + a6be79e) — Ajustes muestra el copy español del
  rechazo SSRF en vez de "API error 422"; tarifa de
  meta-llama/llama-3.3-70b-instruct agregada al mapa (verificada en la fuente
  primaria de OpenRouter: $0.10/$0.32 por millón).
B6 ✓ guardián del gate duplicado + cobertura (31017c5 + d6ae7ad + c1c2037) —
  test de paridad entre el espejo del cliente (`modelGate.ts`) y
  `_UNRESTRICTED_PROVIDERS` del servidor, verificado inyectando un drift a
  propósito (el test falla y nombra ambos lados); caso restringido del gate
  (openrouter + modelo arbitrario → 422; y el modelo resuelto es el que se
  reenvía a `build_provider`); y normalización del provider_type guardado
  desconocido (higiene de estado: el síntoma que describía el advisory NO
  reproduce, porque RHF valida los radios desde el DOM).
REVIEWS NATIVAS: aprobadas en WU1/WU2/WU4/B1/B2; sin review en WU3 (sin receipt),
WU5 (#4655), B2-advisories, B3, B4 y B6 → entrega por política ordinaria del repo.
PENDIENTE: B5 (deuda de review/proceso). El ROADMAP quedó: (1) ✓ HECHO — fusión de
Settings + wizard (16/10, main @ 642fbe5, PR #21); (2) PERFIL — primera entrega ✓
(19/10, main @ 711cf2a) y sus FUNCIONES ya están DECIDIDAS (19/10, sesión 23:
orden vigente **T7a ✓ → T3 → T2 → T6 → T5 → T4 → T1 → T7b**, ficha
odd/tasks/profile-roadmap.md); **T7a (preferencias) ✓ ENTREGADA Y PUSHEADA el
26/10** (main @ fcb2047). El dashboard de uso/costos pasó a ser la obra T4 del
perfil; los defaults de análisis siguen sin dueño. El REPINTADO tiene dueño y
lugar: es **T7b**, ÚLTIMO del orden (ver "inventario de inconsistencias" en
Transversal).

REVIEW NATIVO DEL PERFIL (19/10): ✓ **state approved** y autoridad quemada
(`gentle-ai.review-acknowledged/v1`) — el primer review nativo que CIERRA en esta
máquina desde el 16/10. Candidato: el rango commiteado de la sección
(`642fbe5..711cf2a`, 14 archivos, 1133 líneas, tier high por señal `auth`),
4 lentes por `pi_host_relay`. Resultado: **0 blockers, 5 WARNING y 12 SUGGESTION**,
los 17 con disposición `informational`; ninguna corrección abierta, y el provider
pide tratarlos como trabajo posterior, NUNCA como motivo para re-correr el review
de este candidato. Registro: `odd/tasks/profile-section-review-followups.md`.
Lo que cambió para B5: **el frente de review ya no está uniformemente bloqueado**.
Lo que queda ahí es la lineage vieja de WU3 (correction_required sin receipt),
WU5 (#4655) y el candidato de `d7e9b50` (la fusión), que sí quedó sin review.

Análisis (Archives):
✓ SECCIÓN CERRADA (02/10 sesión 21). Plan paso a paso A1→A4 completo:
  A1 ✓ fundaciones backend (70cc276, sesión 18): el análisis sobrevive al
    borrado de la sesión (migración 0005: chat_session nullable + ON DELETE
    SET NULL), snapshot completo y en orden, caps.
  A2 ✓ guardar análisis desde el chat (e3d6901, sesión 19): SaveAnalysisDialog
    cablea useCreateArchive desde el composer.
  A3 ✓ reconstrucción de la lista al diseño (0c4d9a8, sesión 20): búsqueda,
    orden, tarjetas con archivo/tiempo relativo/resumen y detalle lazy + el
    backend mínimo de enriquecimiento (ArchiveListItem con files/row_count/
    column_count); follow-up de tipos nullable (9540c63).
  A4 ✓ CICLO DE VIDA COMPLETO (cb6c5e9 + e0d2d14, sesión 21):
    - Reabrir = sesión viva si existe (navega a /app/chat/{id}); fallback a
      snapshot de SOLO LECTURA si la sesión fue borrada (chat_session NULL).
    - Exportar = Markdown del snapshot completo, 100% client-side.
    - Renombrar (PATCH) + Borrar (DELETE, con ConfirmDialog) + paginación
      keyset (limit/before, page 50) con «Cargar más».
    - Nuevos: web/src/lib/archiveMarkdown.ts, web/src/components/
      ArchiveSnapshot.tsx; `useArchives` pasó a useInfiniteQuery.
    - Verificación: verificador independiente adversarial PASS WITH FINDINGS →
      corrección → re-verificación; RDD nativo declinado por el usuario
      (declined_this_candidate); validación EN VIVO OK.
    - Limitación conocida: búsqueda/orden client-side sobre las páginas
      cargadas (avisada en la UI). Reportes PDF/HTML siguen en Fase 3.

Transversal:
✗ Multi-cuenta en pestañas (cookies por navegador)
✗ R8 (deferido): server apagado → errores claros
✗ Triage de ~749 archivos sueltos en server/uploads/
✗ Explicaciones aún más al grano (número principal primero)
✗ index.html sin Cache-Control → tabs SPA corren bundles
  viejos sin re-resolver chunks (causó el falso bug de
  paginación del 15/09: "no aparece el botón" era la tab con
  el bundle anterior). Fix estándar: no-cache en index.html
✗ Inventario de inconsistencias de diseño (16/09, tarea 7 —
  insumo del rediseño): dos azules de acento (#007bff chat vs
  #007acc wizard/setup), cuatro grises mute (#888/#999/#666/
  #555), rojos de error (#e74c3c/#c0392b vs #c62828), verdes
  (#28a745 vs #4caf50), azules de selección (#e3f2fd vs
  #e6f3ff), spacing 10px off-grid, mezcla de notación hex y
  radii num/string
  ⚠ YA NO ESTÁ HUÉRFANO (resuelto 19/10, sesión 23): este inventario era
  "insumo del rediseño" y el rediseño NUNCA se ejecutó — la app sigue con el
  estilo viejo y web/src/design/tokens.ts es la base, no la aplicación. La
  decisión pendiente se cerró: el REPINTADO con Dark Cockpit es la obra **T7b**
  de `odd/tasks/profile-roadmap.md`, con **PERFIL como pantalla piloto** (la más
  chica y autocontenida), y va **ÚLTIMA** del orden (T7a → T3 → T2 → T6 → T5 →
  T4 → T1 → T7b): el maintainer priorizó funcionalidad primero y cirugía después.
  La primera entrega del perfil lo dejó a la vista: se modernizó solo el bloque
  de usuario del sidebar y el resto quedó igual, a propósito.

═══════════════════════════════════════════════════════
FASE 2 — DATOS DEL MUNDO REAL  [OBJETIVO #3 COMPLETO]
═══════════════════════════════════════════════════════
De "CSV limpio de prueba" a "el archivo feo del trabajo".

✗ MULTI-DATASET: cruce y análisis de varios archivos a la vez
  (merge/join guiado por el LLM con contexto de todos los perfiles)
✗ Encodings raros (latin-1, sep=";", separadores de miles)
✗ Fechas mixtas en una misma columna
✗ Excel multi-hoja (elegir/combinar hojas)
✗ Archivos grandes: streaming/muestreo con aviso claro
✗ Perfilado avanzado: outliers, duplicados exactos y difusos

═══════════════════════════════════════════════════════
FASE 3 — FLUJO DE TRABAJO PROFESIONAL  [OBJETIVO #4]
═══════════════════════════════════════════════════════
Del análisis al entregable y la velocidad power-user.

✗ Reportes: sesión de preguntas → entregable PDF/HTML para el
  stakeholder, con anotaciones del analista (con diseño visual
  propio del entregable). SEMILLA YA PLANTADA: la pestaña
  Archives hoy snapshottea la sesión completa (mensajes + código
  + artefactos + archivos, CRUD con ownership) — esta fase la
  convierte en el reporte exportable
✗ Archives: exportar/compartir el snapshot + anotaciones del
  analista sobre mensajes puntuales
✗ Errores que enseñan: ver código + error y CORREGIR la
  instrucción (editar y re-ejecutar, nada de reintentos mudos)
✗ Atajos de teclado y búsqueda rápida de columnas
  (teclado primero — público profesional)
✗ Historial de sesiones: buscar, etiquetar, organizar

═══════════════════════════════════════════════════════
FASE 4 — PRIVACIDAD COMO CUÑA COMPETITIVA  [OBJETIVO #5]
═══════════════════════════════════════════════════════
"Los datos sensibles no salen de tu máquina".

◐ Proveedor local: la base ya es OpenAI-compatible (base_url +
  presets ollama/lmstudio en el wizard); falta PROBAR EN VIVO
  contra Ollama / LM Studio y documentar (F1 de Ronda 8 quedó
  diferido: sin proveedor local instalado — receta en checklist)
✗ Adaptadores NATIVOS de proveedores (Anthropic, Gemini, Azure/
  Bedrock): arquitectura de adapters sobre el provider protocol
  (el wizard de presets de Fase 1 ya deja elegido el proveedor;
  acá se conectan los que no hablan OpenAI)
✗ Sandbox Docker (pregunta abierta: ¿v1 o v2? — decidir aquí)
✗ Multiplataforma del sandbox (hoy POSIX; ¿Windows nativo?)
✗ Auditoría de privacidad: qué sale hacia el proveedor de LLM
  (¿enviar solo perfiles + muestras? modo "nada sale")

═══════════════════════════════════════════════════════
FASE 5 — NEGOCIO  [OBJETIVO #6 — DIRECCIÓN ABIERTA]
═══════════════════════════════════════════════════════
Solo cuando el producto de las fases 1-4 sostenga la promesa.

✗ Open-core: empaquetar el núcleo local GRATIS (instalador,
  docs, README público) — embudo y reputación
✗ Hosted: versión paga individual (suscripción = fricción cero)
✗ Backend de la HOSTED en Supabase (Postgres + auth + storage +
  realtime). REGLA: la versión LOCAL no usa nube — la privacidad
  es la cuña. Para que el swap sea barato: la persistencia vive
  detrás de la interfaz del store (hoy SqliteStore) — NUNCA
  filtrar SQL/SQLite fuera de esa capa. La feature realtime de
  Fase 1 se hace con SSE sin acoplarse, dejando a Supabase
  realtime como candidato natural de la hosted.
✗ Equipos/organizaciones (B2B por asiento — la plata grande,
  más adelante)

═══════════════════════════════════════════════════════
PREGUNTAS ABIERTAS DE LA VISIÓN — ESTADO
═══════════════════════════════════════════════════════
✓ Timeline de auth → resuelto de facto (login en Fase 0)
✓ Svelte vs React → resuelto (React + Vite en el repo)
✗ Sandbox Docker ¿v1 o v2? → decidir antes de Fase 4
✗ Umbrales de perfilado (muestra vs scan completo) → Fase 2
✗ Alcance multiplataforma (¿Windows fuera de v1?) → Fase 4
✗ Límite exacto core/server → revisar al empaquetar (Fase 5)

═══════════════════════════════════════════════════════
CRITERIO DE "OBJETIVOS CUMPLIDOS" (checklist final)
═══════════════════════════════════════════════════════
[ ] 1. Un analista resuelve su día de preguntas sin fricción
[ ] 2. Toda respuesta es trazable, computada y con rigor (n, %)
[ ] 3. Come los archivos feos reales y cruza varios a la vez
[ ] 4. Retoma trabajo, itera encadenado y entrega un reporte
[ ] 5. Corre 100% local con proveedor a elección (privacidad)
[ ] 6. Open-core + hosted viven y la local alimenta a la hosted

─────────────────────────────────────────────
REGISTRO DE HITOS (contexto global de la construcción)
─────────────────────────────────────────────
- 31/08: SDD inicial; propuesta "datara-2-rework" (open-core,
  arquitectura limpia, auditoría del viejo Datara heredada).
- 01-02/09: implementación del rework completo (auth real, loop
  de chat con sandbox, uploads con perfilado, frontend React)
  + change "frontend-ux-stability" (estabilidad de navegación).
- 03/09: RONDAS QA 1-2 — 8 bugs triageados y arreglados; nace
  el checklist de validación en el Escritorio.
- 04/09 mañana: RONDA 3 — fix de fechas del sandbox confirmado
  en real (pregunta larga y dos gráficos verdes); hallazgo de
  respuestas incompletas → se surfacea el stdout del sandbox.
- 04/09 tarde: RONDA 4 cerrada 5/5 → R1-R8 TODOS VERDES. Fix
  del bug estructural del sandbox (exec de dos dicts → NameError
  intermitente desde 4 rondas). Ruta de construcción escrita.
  Decisiones anotadas: Supabase para la hosted, wizard de
  proveedores (presets F1 / adaptadores F4), Archives madura a
  reportes en F3, diseño visual en F1.
- 04/09 cierre: primer change SDD de FASE 1 entregado a main —
  cinturón completo (fitness test de arquitectura + bench de
  regresión con 10 preguntas reales). El bench validó el flujo
  completo con ~$0.006 de créditos y cazó 3 bugs (uno de producto).
- 05/09: REALTIME completo de punta a punta: fix del orden del
  chat confirmado; change SDD "realtime" (spec 22 escenarios →
  3 PRs apilados → verify pass_with_warnings → archive); repo
  publicado en github.com/Dandlrt09/Datara-2 y 3 PRs mergeados.
  Validación en vivo de dos pestañas con LLM real: punto verde
  cruzado entre tabs confirmado. 2 bugs de integración cazados
  en runtime (ninguno visible para los tests) y arreglados con
  regresión: c3bb172 (STREAMING_ENDED en camino de error) y
  f52b76f (sidebar muerto con cache inicial vacío) + 169a6a9
  (prompt plotly-only). Limpieza: ramas remotas borradas,
  usuario QA eliminado de la DB.
- 07/09: Fase 1 sesión 2 — seed kwarg, cancelar subida,
  reintentos persistentes (0fb4345..95b2601). Ronda 5 cerrada
  (A y B verdes con verificación server-side). Repro de RIGOR
  documentado. RIGOR movimiento 1 entregado (be704a9, 25cdca5,
  178a54f/541aacd): bench 10/10 con el PROMPT REAL; re-test
  manual del repro ✓✓.
- 08/09: RIGOR movimiento 2 end-to-end (SDD rigor-mov2: 8
  commits f8fa796..9038ce3; Ronda 6 con 4 correcciones en vivo;
  pytest 357/357; bench 11/11) — narrativa con valores EXACTOS,
  veredicto "respuesta de analista". Higiene: AGENTS.md
  (1c58a96) + 409 mismo-nombre (fb15556) + sweep de uploads
  (6a0e31b) + tests aislados del uploads real (ac56988).
- 09-11/09: MOVIMIENTO 3 — wizard first-run con SDD completo
  (mov3-ui-wizard): spec 16 escenarios → design 8 decisiones →
  11 tareas → PRs #4/#5 mergeados (4e71653, c9e25e3). Verify
  inline cazó 1 CRITICAL (remediado). Ronda 7 A/B/C verde con
  fix en vivo (d5653bf). Archive obs #200. Ruta actualizada:
  nace FASE 1.5 (pulido por sección, QoL).
- 12-14/09: SETTINGS PROVIDER WIZARD con SDD completo
  (settings-provider-wizard): planning (obs 210-214) → apply
  WU1-6 con patrón no-reset (presupuestos realistas en el
  ledger + corrección inline; WU5+6 en un solo ciclo) → PRs
  #6-#13 squash-mergeados (main @ c273062) → verify PASS
  (backend 416/416) → archive. Ronda 8: checklist reescrito
  con pasos explícitos (QUÉ/CÓMO/ESPERADO/SI FALLA),wizard
  end-to-end y endpoint /models validados en vivo por el
  usuario A-G verde (F1 diferido). Mejora nacida en la ronda:
   buscador de modelos en el wizard (6af03c0, Ronda 8 verde).
   2 nits UX a Fase 1.5. Fase 1 queda SOLO con diseño visual.
- 14/09 tarde: FASE 1 DISEÑO VISUAL EN CURSO — design system
  "Dark Cockpit" definido y aprobado (dark casi negro + acento
  azul único #2E7DFF, Inter + JetBrains Mono, glass solo en
  overlays; proyecto Stitch "Datara 2"). Pantallas Chat y
  Archivos aprobadas (canónicas en repo /Pantallas). Nav
  definitiva: Chat / Archivos / Análisis / Ajustes. Fase 1.5
  siembra nueva: pulir Login + sección de perfil de usuario.
- 14/09 cierre: SET PRIMARIO DE 6 PANTALLAS COMPLETO Y AUDITADO
  (Chat, Archivos, Análisis, Ajustes, Login, Registro — canónicas
- 15/09: FASE 1 DISEÑO VISUAL CERRADO — set completo de 18
  pantallas canónicas en /Pantallas/*.txt (+previews): 6
  primarias + 3 estados (vacío/generando/error) + 5 wizard de
  proveedores + modal de tipado de columnas + 2 responsive
  (rail tablet / drawer móvil) + chat con gráfico + perfil.
  Metodología consolidada: chat.txt / ajustes.txt como plantilla
  ancla (shell byte-a-byte; generación Stitch = solo contenido,
  después sync de head+sidebar). DESIGN.md v4.1 local con
  sección States + Charts multi-serie (rampa = solo colores del
  sistema). Pendiente menor no bloqueante: resync del doc a
  Stitch (acumula: sección Charts + typo "560py" en States).
- 15/09 tarde: FASE 1.5 INICIADA — inventario completo de
  funcionalidades de chat (backend+frontend) + triage de pulido
  con Claude verificado punto por punto contra el código (8
  hallazgos: sin disparador de abort, run_code no mata el
  subprocess al cancelar, code persistido pero no renderizado,
  sin PATCH de rename, tokens/costo solo en DB, sin copiar ni
  descargas). Orden de 7 tareas aprobado por el usuario y
  persistido en la sección Chat de Fase 1.5. Arranca: botón
  Detener.
- 16/09: FASE 1.5 CHAT — BACKLOG 7/7 COMPLETO. Validación en
  vivo de descargas (d963f3d; decisión CSV: coma estándar) +
  fix locale del sandbox (4cc9046, repro del 15/09 cerrado) +
  rename de sesiones (86963d8, PATCH + TITLED + editor inline)
  + tokens/costo por mensaje (5446a93) + tokens de diseño
  (6ef299a, cero cambio visual). Suites: backend 427/427 ·
  web 183/183 · main @ 6ef299a. Proceso: ODD adoptado (gentle-ai
  v3.0.0) y RDD activado GLOBAL (el ON solo existe global;
  clone-local solo apaga). Ops aprendidas: uvicorn sin --reload
  en /mnt/c (inotify no funciona en drvfs — reiniciar el server
  tras cada cambio de backend ANTES de validar); suites largas
  siempre en foreground. Siguiente obra de chat: ROBUSTEZ
  model-agnóstica (ver Chat), luego inventario funcional →
  cierre de sección → FILES.

- 16/09 (sesión 2): SDD FORMAL ESTRENADO — change chat-robustez.
  Preflight: interactive + engram-only + ask-on-risk; cadena
  stacked-to-main. Planificación completa con gatekeeper por
  fase, todo en engram: proposal #304 · spec #305 + enmienda #307
  (22 reqs / 37 escenarios) · design #306 (6 work units) ·
  tasks #308 (22 tareas en 7 fases). Slice 1/5 (WU1 taxonomía de
  errores + WU2 retry JSON con feedback): rama
  feat/chat-robustez-pr1-taxonomy @ d3eaf80, 8 archivos,
  631+/10-, backend 458/458 verde (427 + 31 nuevos). PR1
  aceptado con size:exception (641 líneas, 69% tests) por
  decisión del maintainer. NO pusheado aún: gh no está instalado
  (el PR se abre por la UI web o instalando gh).
  Aprendizajes de la sesión: (1) los tests dominan el conteo de
  líneas — el forecast de tasks erró por 3x al contar solo
  producción; (2) vitest NO acepta flags de Jest como
  --testPathPattern → el filtro correcto es posicional
  (npm test -- <token>); (3) el bloque "SDD Session Preflight"
  nunca se escribe a mano: el runtime lo prepende y el
  dispatcher rechaza el texto model-authored; (4) la caché de
  testing de SDD init estaba stale (del 31/08, repo vacío) y se
  refrescó: strict_tdd sigue false, pero por una razón mecánica
  (no hay comando raíz que agregue pytest + vitest), no cultural.
  Próximo: slices 2-5 (repair pass → tokens/frontend → bench →
  validación en vivo con costo real de provider).

- 17/09 (sesión 3): upgrade gentle-ai v3.0.0 → v3.1.0 + sync
  aplicado (3 archivos: chained-pr SKILL.md, work-unit-commits
  SKILL.md, opencode.json). ODD step 6 ahora cierra cada tarea
  con un commit work-unit en la rama de feature (tests y docs
  junto al comportamiento, Conventional Commit, identidad del
  commit registrada como evidencia en el feature document) y el
  review nativo pasa a ser por commit o por slice
  (assess --base-ref <último límite revisado> --committed-only;
  high → inmediato, medium → diferido al cierre del slice
  ~400 líneas). La estrategia de entrega con cadenas de PR ahora
  aplica también a trabajo orgánico, no solo SDD. Sin breaking
  changes; provider contract sigue 1.2.0. Los assets nuevos rigen
  a partir de la próxima sesión (el contrato se carga al arrancar).
  Hallazgos del día: (1) gh SÍ está instalado —
  /mnt/c/Program Files/GitHub CLI/gh.exe, autenticado como
  Dandlrt09 con scope repo → corrige la nota del 16/09: los PRs
  SÍ se pueden abrir desde el orquestador; (2) el dispatcher SDD
  nativo NO resuelve changes engram-only en este repo: siempre
  devuelve artifactStore=openspec apuntando a <repo>/openspec
  (inexistente), nextRecommended=sdd-new y blockedReasons
  "Active OpenSpec change not found" — verificado con 4 changes
  (chat-robustez, settings-provider-wizard, mov3-ui-wizard,
  chat-regression-bench). No hay forma de declararle el store
  (--store no existe, GENTLE_AI_SDD_STORE no hace nada). Implica
  que las obras SDD previas corrieron sin dispatcher nativo.
  Pendiente de resolver.
  Próximo: slices 2-5 de chat-robustez (PR1 local @ d3eaf80, sin
  pushear) → push + apertura de PRs de la cadena stacked-to-main.

- 23-24/09 (sesión 4): CHAT CERRADO. Los 2 pendientes de ciclo de
  vida de sesiones cross-tab (eventos CREATED/UPDATED/DELETED +
  is_streaming) y el ítem #7 (editar pregunta → truncar +
  re-preguntar; Regenerar reusa el path de edición) quedaron
  implementados, validados EN VIVO por el usuario y pusheados a
  main (435fd03). La sección Chat de Fase 1.5 queda CERRADA.
  Luego: INVENTARIO FUNCIONAL DE FILES, con el orquestador +
  mapeo por subagente y verificado punto por punto contra el
  código (endpoints, hooks, perfil, delete, límites). Triage
  priorizado en 4 tiers y persistido en la sección Files.
  Correcciones al análisis previo: (a) la cancelación del wizard
  SÍ funciona por botón (UploadStep tiene su propio AbortController),
  el hueco real es el abort desde el PADRE (WizardOverlay); (b) el
  body NO se carga entero antes de tocar disco (Starlette
  spool-ea el UploadFile), el blowup real es await file.read() +
  parse; (c) gap NO visto antes: falta UNIQUE(user_id,
  chat_session, filename) → race de duplicados con storage_path
  compartido. Próximo: ejecutar el orden de Files desde el TIER 0.

- 24/09 (sesión 5): FILES TIER 0 — F1 CERRADO Y PUSHEADO (0b70605).
  Límites de subida end-to-end: cap streaming (fin del read()
  entero a RAM), fast-reject por Content-Length, guard PRE-PARSE
  del zip XLSX, backstop post-parse, cuotas sesión/usuario, topes
  por env DATARA_MAX_* (100MB/500MB/1GB/5GB). 8 tests nuevos;
  suite completa 598/598 verde. Validación EN VIVO del usuario en
  4 pruebas, verificadas server-side (log de acceso + DB + disco):
  happy path 201 + perfil; cap por tamaño desde la UI con tope
  1000B → 413; cuota de sesión (q1 201 → q2 413); expansión XLSX
  → 413. En los TRES rechazos: cero huérfanos en disco y cero
  filas en la DB. Bonus: delete (archivo y sesión) intacto.
  La revisión RDD de este candidato NO pudo completarse: el
  consentimiento se dio y el START creó la transacción (lineage
  review-e8eb1018a120e2d0), pero el transport de opencode rechaza
  el binding que su propio STATUS emite
  (opencode_review_transport_binding_invalid), reproducido por el
  host (2 veces) y alimentando el prompt byte-exacto directo al
  transport (2 veces), desde dos directorios → cwd-independiente;
  doctor sano y assets = binario 3.7.0. Lookup definitivo
  open+closed → canonical #4030 (OPEN, status:needs-review → sin
  fix publicado); los otros abiertos (#4293, #4516 git-less
  parent, #4421 artifact-subject, #4909 sibling worktree) tienen
  causas distintas. Se reportó UNA ocurrencia scrubbed sin tocar
  labels (comentario 5818673362) y se ejecutó el decline capturado
  (declined_this_candidate, target match). Candidato NO revisado;
  la entrega siguió la política normal del repo.
  HALLAZGO del análisis técnico posterior: el body del upload se
  spollea a temporal ANTES del chequeo de auth (fastapi
  routing.py:430 vs :481) → el camino NO autenticado también
  puede llenar /tmp. Siembra F1.1.
- 24/09 (sesión 6): FILES TIER 1 — F2 CERRADO Y PUSHEADO (1d5acf7,
  0b70605..1d5acf7). UNIQUE(user_id, chat_session, filename) real +
  IntegrityError→409: migración 0003 con dedupe (conserva el id más
  bajo) + purga de profiles huérfanos + CREATE UNIQUE INDEX; el store
  traduce IntegrityError → DuplicateError (rollback primero) y la ruta
  responde 409 con el MISMO detail del pre-check vía helper compartido.
  Hallazgo clave del diseño: los bytes se escriben en dest_path ANTES
  del INSERT, así que el perdedor de la race NO debe desvincular — si
  lo hiciera, borraría el archivo del ganador; eso habría cambiado un
  bug de datos por otro. Se descartó el rediseño temp-file + os.replace
  por desproporcionado sobre el path que F1 acababa de validar.
  7 archivos +190/-33; suite backend 601/601 (focus files 42/42);
  validado EN VIVO por el usuario; migración probada sobre una COPIA
  de la DB real (1,2 → 1,2,3, índice presente, los 2 archivos reales
  intactos, INSERT duplicado rechazado). El test de la race es
  determinista (monkeypatch de get_file_by_name para saltear el
  pre-check), no un test de timing con threads. La revisión RDD de F2
  no corrió: el preflight sin selector ya ve el worktree vacío (todo
  commiteado) y su único paso pendiente era declarar scope de
  untracked, no el commit; más el mismo defecto #4030 del transport.
  OPS: Engram empezó a rechazar memorias con
  "ambiguous_active_runtime_sessions" porque había 9 sesiones de días
  anteriores sin cerrar (ended_at NULL + lease NULL, o sea "sin
  información"); cerrarlas con mem_session_end dejó el doctor en
  9 ok / 0 warnings.
  Próximo: TIER 1 F3 (Excel multi-hoja).
- 24/09 (sesión 7): FILES TIER 1 — F1.1 CERRADO Y PUSHEADO (1a093df,
  1d5acf7..1a093df). Guard de body acotado al upload: middleware ASGI
  puro (server/api/upload_guard.py) que rechaza por Content-Length
  ANTES de que Starlette parsee/spoolee el multipart — 413 sobre
  max+margen, 411 si falta Content-Length (variante elegida por el
  usuario: cierra el bypass chunked; el SPA siempre lo manda), 400 si
  malformado. Registrado en main.py antes de CORS; margen y mensaje
  compartidos con el fallback del handler para que no diverjan. Cierra
  el residual de F1 incluido el camino NO autenticado (antes: el body
  se spolleaba a /tmp y recién después daba 401). 5 archivos +243/-16;
  focused files 44/44, suite backend 603/603; validado EN VIVO por el
  usuario (2MB no-auth → 413, chunked → 411, cero disco).
  La revisión RDD de F1.1 tampoco corrió: START abrió la transacción
  (medium, 1 lens review-reliability) pero el transport de OpenCode
  volvió a rechazar el binding que su propio STATUS emitió
  (opencode_review_transport_binding_invalid) — 8ª ocurrencia del
  canónico #4030, con una ocurrencia scrubbed agregada
  (issuecomment-5823781833, sin tocar labels) y el candidato declinado
  con la invocación capturada (target match). Estado tras el decline:
  el selectorless STATUS vuelve a unrelated/start.
  OPS: gh NO está en el PATH del shell WSL — se usó
  "/mnt/c/Program Files/GitHub CLI/gh.exe" (autenticado).
  Próximo: TIER 1 F3 (Excel multi-hoja: perfilar todas las hojas +
  endpoint de selección + aviso de hojas extra).
- 18-22/09 (sesiones intermedias): cerraron los slices 2-5 de
  chat-robustez (taxonomía #14, repair pass #15, tokens de error
  #16, códigos tipados en banners #17), mejoras de bench (#18-#20,
  selección de modelo + cobertura honesta), costo por-millón de
  tokens con fallback honesto para modelos sin precio, separadores
  ES en la narrativa, cifrado de API keys en reposo (c30a36d),
  persistencia atómica de files+profiles (2b91f50), flag de
  archivos sin perfil (3e33bc8) y tabla de resultado única en
  sandbox/prompt (95ffe58). Evidencia: git log 18-22/09.
- 25/09: FILES TIER 1-2 — F3, F4, F5, F6, F7 CERRADOS Y PUSHEADOS
  en la misma jornada. F3 (5fa1024) Excel multi-hoja con picker +
  hoja activa reprofilada; F4 (f8fbfa6) confirmación de delete;
  F5 (796423b + 0641402) abort del upload del wizard; F6 (6b31b08)
  UI alineada a la allow-list del server (sin .tab); F7 (49c1982)
  tipos del cliente alineados a los modelos Pydantic. Todos:
  verificación RDD-off independiente PASS/PASS-WITH-FINDINGS +
  validación EN VIVO del usuario + push. La revisión RDD nativa NO
  corrió en ninguno: el transport de OpenCode rechazó el binding de
  su propio STATUS (opencode_review_transport_binding_invalid,
  clase canónica #4030, open sin fix publicado) — varias
  ocurrencias más registradas; todos los candidatos declinados con
  la invocación capturada y sin PASS fabricado.
- 28/09: FILES TIER 3 — F8 (f5d3bfe) offload de pandas con
  asyncio.to_thread; F9 (c86b519) vista de perfil tabulada
  (ProfileTable). Ambos verificados RDD-off + validados en vivo +
  pusheados.
- 29/09 (sesión 11): FILES TIER 3 — F10 CERRADO Y PUSHEADO
  (2613f08 backend + 86d7bae frontend): paginación keyset en ambos
  listados de files + botón "Cargar más" en la tabla global.
  Backend 632, web 329, build ✓. Revisión RDD nativa intentada
  (lineage review-e132e45d439e9176, consent granted) → reviewer
  falló x2 por el defecto de transport → terminal
  stop/unachievable_lens_slot; fallback RDD-off PASS WITH FINDINGS;
  validación EN VIVO del usuario OK (50 + 3, sin duplicados).
  TIER 0-3 de Files COMPLETOS. Próximo: F11 (re-descarga del
  original).
- 29/09 (sesión 12): FILES TIER 4 — F11 CERRADO Y PUSHEADO
  (09da35f backend + 7d26899 frontend): GET /api/files/{id}/download
  con ownership + contención + Content-Disposition/Content-Type, y
  acción "Descargar" por fila en la tabla de Files. 5 archivos +386;
  backend 642, web 332, build ✓. Revisión RDD nativa intentada
  (lineage review-7b68f128682d65aa, consent granted) → reviewer Task
  rechazado x2 por opencode_review_transport_binding_invalid (canónico
  #4030) → unachievable; el STATUS siguiente quedó terminal
  (operation_timeout, retry_safe=false, sin mutación) → fallback
  RDD-off medium PASS WITH FINDINGS (falsado por regresión inyectada);
  verificación end-to-end por HTTP (bytes idénticos, headers, 404
   ajeno, 401 sin cookie) + validación EN VIVO OK. Próximo: F12.
- 29/09 (sesión 13): FILES TIER 4 — F12 CERRADO Y PUSHEADO (605c71f
  backend + 206de3f frontend + 6615a43 migración): rename de archivo
  por PATCH /api/files/{id} con editor inline "Renombrar" en la tabla
  de Files. 200/401/404/409/422, texto de duplicado COMPARTIDO con el
  upload, extensión inmutable, disco intacto. La validación EN VIVO del
  usuario cazó que una sola mayúscula esquivaba la unicidad (agujero
  previo, también en el upload) → F12.1: casefold en la app + migración
  0004 con idx_files_unique_name COLLATE NOCASE y guard no destructivo,
  ejercitado sobre la DB real (renombró un perdedor, no borró nada).
  Backend 672, Files 106, migraciones 11, web 339, build ✓; E2E HTTP
  14/14 + 9/9 del fix; verificador independiente PASS WITH FINDINGS y
  corrección probada por inyección. RDD nativo: el usuario eligió
  "Saltear esta vez" (decline candidate-scoped, sin registro de
  review). Próximo: TIER 4 F13 (nits).
- 29/09 (sesión 14): FILES TIER 4 — F13 CERRADO Y PUSHEADO (314bb2c
  backend + a06d554 frontend): nits de tablas. Tabla vacía → "Sin
  resultados"; total_rows del frame + aviso "Mostrando las primeras 20
  de N filas."; formateador ES (formatNumbers.ts, ICU-free) en la tabla
  de resultado, la de perfil y la lista de Files, con orden y CSV crudos.
  Decisión de producto: español en TODAS las tablas. Backend 674, web
  354, build ✓. RDD nativo: decline candidate-scoped del usuario
  ("Saltear esta vez"); fallback RDD-off high + verificador independiente
  PASS WITH FINDINGS (sin BLOCKER/CRITICAL); validación EN VIVO de los
  3 nits OK. TIER 0-4 de Files COMPLETOS. Al cierre, el usuario reportó
  el problema de la lista GLOBAL (no cambia al cambiar de sesión) → se
  sembró F14 (lista de Files por sesión) para una sesión NUEVA, con 3
  opciones de diseño A/B/C a decidir. Próximo: F14 + FASE 1.5 restante
  (Wizard / Settings wizard / Perfil·Settings hub).

- 29/09 (sesión 15): FILES F14 CERRADO Y PUSHEADO (2e28f08): la lista de
  Files ahora reacciona a la sesión elegida. Decisión de producto: opción B
  (global + filtro "Solo esta sesión" / "Todas las sesiones", default solo
  esta sesión). useFiles(sessionId) quedó paginado por cursor y comparte un
  único motor con useFilesGlobal(); un solo activeList maneja empty
  state/paginación/error por vista; useFilesGlobal y el trigger del wizard
  intactos. 5 archivos +514/-255; focused 79, web 365, build ✓; validación
  EN VIVO OK. RDD nativo falló de nuevo por #4030 (6ª+ reproducción): reporte
  autorizado por el usuario → 1 ocurrencia (issuecomment-5900744641); decline
  candidate-scoped + fallback RDD-off medium + verificador independiente
  read-only PASS WITH FINDINGS (0 BLOCKER/CRITICAL). Próximo: FASE 1.5
  restante (Wizard / Settings wizard / Perfil·Settings hub).

- 01/10 (sesión 16): NITS DEL WIZARD CERRADOS Y PUSHEADOS (d42f53e "gate
  auto-open on in-flight session creation", 9853de3 "engage the latch when
  a file is dropped", 8f1e284 "cover inert datara.wizard keys after a
  rollback"; push 2e28f08..8f1e284 a main). Los 3 nits: (1) gate
  session-creation pending en triggerHolds (mutationKey ["createSession"] +
  useIsMutating — react-query v5 tiene estado de mutación por-instancia);
  (2) setEngaged sincrónico al soltar archivo (design D3); (3) test runtime
  de keys inertes tras rollback (wizardRollbackInert.test.tsx). 6 archivos
  web-only (3 prod + 3 tests); web 376/376, build ✓; verificador
  independiente PASS WITH FINDINGS (0 BLOCKER/CRITICAL) + corrección acotada
  de fuerza de test (inyección probada). RDD: consent v3 medium → el usuario
  eligió "Saltear esta vez" (decline candidate-scoped, sin registro) →
  fallback RDD-off medium. SECCIÓN FILES ✓ CERRADA. Decisión de producto
  nueva: generalizar las 3 preguntas sugeridas del paso Question (hoy fijas
  y de dominio retail) derivándolas del perfilado (opción B, determinista,
  sin LLM) — ítem NUEVO para sesión nueva. Próximo: Settings wizard /
  Perfil·Settings hub + el ítem de sugerencias.

- 01/10 (sesión 17): WIZARD — SUGERENCIAS DESDE EL PERFILADO + FIX DE
  REUSE, CERRADOS Y PUSHEADOS (2af95f4 "feat(wizard): derive suggested
  questions from the dataset profile"; 4db7317 "fix(chat): re-apply wizard
  suggested questions on reuse"; push 8f1e284..4db7317 a main). (a) Las 3
  preguntas del paso Question ya NO son fijas de retail: buildSuggestions
  (profile) las deriva del perfilado (dtype + cardinalidad), determinista y
  SIN LLM, con fallbacks genéricos; el fileId se threadea Upload →
  WizardOverlay → QuestionStep (single-sheet y multi-hoja) y el perfil se
  lee vía useProfile. (b) Bug cazado por el usuario en validación EN VIVO:
  reusar el wizard no precargaba la segunda pregunta — causa:
  consumedSuggestedQuestionRef era un latch one-shot que nunca se reseteaba
  en ChatView (navegar A→B sin remontar); fix: eliminarlo y aplicar la
  sugerencia cuando location.state la trae. El test previo era TRUCHO (no
  navegaba); reemplazado por uno real con MemoryRouter + useNavigate
  (inyección probada: falla con el latch viejo). web 397/397, build ✓;
  verificador independiente PASS WITH FINDINGS (0 BLOCKER; MINOR de
  cobertura de fileId corregido con test). RDD: consent v3 medium → el
  usuario eligió "Saltear esta vez" (decline candidate-scoped) → fallback
  RDD-off medium. Próximo: SECCIÓN ANÁLISIS, ítem A1 (fundaciones backend),
  paso a paso A1→A4.

- 01/10 (sesión 18): ANÁLISIS A1 — FUNDACIONES BACKEND, CERRADO Y PUSHEADO
  (70cc276 "feat(archives): make analyses durable, complete, and bounded";
  push 4db7317..70cc276 a main; 5 archivos, +329/-19). Cuatro defectos de
  fondo resueltos: (1) migración 0005 hace que el análisis sobreviva al
  borrado de la sesión — SQLite no soporta DROP CONSTRAINT, así que es un
  rebuild de tabla (chat_session nullable + ON DELETE SET NULL; user_id
  sigue CASCADE) preservando filas/ids + índice idx_archives_user_created;
  (2) list_messages gana keyword-only ascending + limit=None (default
  intacto DESC+LIMIT 50 para los 18 callers) y el snapshot del archive pasa
  a ASC y completo (adiós al limit=500 invertido) con message_count/
  truncated; (3) caps: name 200 (strip → 422), payload 8 MiB (→ 413); (4)
  schemas toleran chat_session null. El fixture de archive solo aplicaba
  0001 → ahora aplica TODAS las migraciones. 30 focused / 681 full backend
  verdes; verificador independiente PASS WITH FINDINGS (0 BLOCKER/CRITICAL/
  MAJOR; MINORs de test aceptados) y live no destructivo sobre copia de la
  DB real OK. RDD: el transporte de OpenCode rechazó el binding del revisor
  de forma reproducible (defecto conocido #4030); el usuario eligió "Seguir
  sin reportar" (decline candidate-scoped) → candidato SIN revisión, entrega
  por política normal. Próximo: A2 (crear análisis desde el chat).

- 02/10 (sesión 19): ANÁLISIS A2 — CREAR DESDE EL CHAT, CERRADO Y PUSHEADO
  (e3d6901 "feat(chat): save an analysis from the composer"; push
  70cc276..e3d6901 a main; 4 archivos, +685). Botón «Guardar análisis» en la
  fila del composer (al lado de «Adjuntar») + diálogo accesible
  `SaveAnalysisDialog` que precarga el nombre con el título de la sesión
  (focus-trap reusado de ConfirmDialog/useFocusTrap, Escape cancela salvo
  durante el guardado, maxLength 200). Gates: sin sesión, streaming (esta
  pestaña o cross-tab), request en vuelo, o sesión sin mensajes. Flujo:
  mutateAsync({chat_session, name}) → cierra diálogo + aviso verde "Análisis
  guardado." con link "Ver análisis"; errores 413/422/404/genérico mapeados
  dentro del diálogo. Copy nuevo en español neutro SIN voseo (el voseo del
  chat queda como inconsistencia abierta, fuera de A2). Cache: useCreateArchive
  ya invalida ["archives"]. Web 420/420, build ✓; verificador independiente
  PASS WITH FINDINGS → corrección acotada (test de gate sin sesión aislado con
  mutation-probe, las 5 ramas de error cubiertas, gate de pending + Escape
  bloqueado durante el guardado) → PASS; validación EN VIVO del usuario OK.
  RDD no completable (transport #4030, 2/2, gentle-ai 4.0.0) → el usuario
  eligió "Seguir sin reportar" (decline post-grant ACEPTADO) → candidato sin
  revisión, entrega por política normal. Próximo: A3 (reconstruir la UI de
  Análisis al diseño).

- 02/10 (sesión 20): ANÁLISIS A3 — UI DE LA LISTA, CERRADO Y PUSHEADO
  (0c4d9a8 "feat(archives): rebuild the list screen with search, cards and lazy
  detail"; push e3d6901..0c4d9a8 a main; 8 archivos, +876/-69). Backend mínimo:
  GET /api/archives deriva por tarjeta `files` (nombres del snapshot),
  `row_count` y `column_count` desde el último artefacto de tabla
  (total_rows / columns; fallback a files[].row_count) con parser guardado (un
  payload_json roto ya no puede tumbar la lista). Frontend: ArchiveList
  reconstruida con búsqueda insensible a mayúsculas/acentos, orden
  «Más recientes»/«Más antiguos», tarjetas (título + chip de archivo +N +
  tiempo relativo «hace 2 días»/«hace 1 semana»/«hace un momento» + resumen
  «N filas · M columnas»), Reabrir/Exportar inertes («Disponible próximamente»)
  y UNA sola llamada useArchiveDetail(expandedId) a nivel lista → N+1 muerto.
  Estados vacío y «No se encontraron análisis». Decisión de producto: estilo
  ACTUAL de la app (inline + tokens claros); el mockup aporta estructura/copy y
  la adopción del design system queda para un análisis global cuando termine el
  pulido. Tests: archive focused 25, web 433, build ✓. Gatekeeper cazó el choque
  Intl numeric auto vs copy del mockup (→ numeric "always"); el verificador
  independiente halló el CRÍTICO del link /app → 404 (corregido a /app/chat) + 2
  WARNINGs (ArchiveDetail Omit; estado sin resultados) → corrección →
  re-verificación PASS sin CRÍTICO/WARNING; validación EN VIVO del usuario OK.
  RDD no completable: esta vez el STATUS nativo falló con operation_timeout
  (pre_native, not_started; distinto del #4030) → el usuario eligió "Continuar
  sin reportar" (decline post-grant ACEPTADO) → candidato sin revisión, entrega
  por política normal. Próximo: A4 (ciclo de vida + semántica Reabrir/Exportar).

- 05/10 (sesión 22): SECCIÓN SETTINGS — AUDITORÍA TERMINADA Y PLAN ABIERTO.
  Se recorrió la sección con lupa contra el código (dos `codegraph_explore` +
  lecturas dirigidas). Veredicto: SIN riesgo de seguridad activo (API key cifrada
  con Fernet, SSRF guard sólido, sin F1/F2 como en Files), pero con un gap de
  DISEÑO: Settings es un subconjunto de Setup. Hallazgos P1-P5 y plan WU1-WU5
  documentados en `odd/tasks/settings-production-readiness.md` (engram obs #507,
  topic `audit/settings-section`). Se localizaron los mockups objetivo
  (`Pantallas/settings/ajustes.txt` hub de Ajustes, `perfil.txt` cuenta) que el
  SettingsView actual no implementa. Corrección de un diagnóstico previo: el
  rechazo de modelo por whitelist NO ocurre al guardar en Settings sino en chat,
  y el footgun está en el wizard (lista viva sin filtrar), no en el dropdown de
  Settings (que sale de la whitelist misma); el banner model_not_allowed no tiene
  botón. Sin escrituras de código. Próximo: resolver las 4 decisiones de producto
  (catálogo de modelos recomendados, guías inline vs externas, política de
  whitelist, destino del wizard) y arrancar WU1.

- 05/10–15/10 (continuación de la sesión 22; el contador de sesiones no quedó
  registrado en estos ítems — el detalle completo, con evidencia y tests, vive en
  `odd/tasks/settings-production-readiness.md`): SECCIÓN SETTINGS COMPLETA.
  Los 5 work units del plan y su backlog post-WU5 salieron en 10 unidades de
  trabajo, todas verificadas, validadas EN VIVO por el maintainer y pusheadas a
  main (main @ c1c2037, 15/10):
  · WU1 (7ccd1cc) hub editable: provider_type/base_url/api_key desde Ajustes sin
    recorrer el wizard (PD4: el wizard sigue siendo el first-run, Ajustes el hub);
    base_url read-only en presets nombrados con "Editar URL"/"Usar predeterminada".
    Review nativo APROBADO.
  · WU2 (db2b9f4) guardar-y-verificar: "Guardado · Conectado" / "Guardé, pero
    falló la conexión: …". Review nativo APROBADO.
  · WU3 (08f54d4) desync de whitelist: el wizard ofrece solo modelos permitidos +
    guard en submit; el banner model_not_allowed ahora apunta a Ajustes. La review
    llegó a correction_required (cazó un CRÍTICO real: whitelist vacía = dead-end
    de setup) → corregido con test; validator caído por transport y STATUS atado
    flaky → lineage SIN receipt, el maintainer eligió commitear igual.
  · WU4 (2b6c6bf) copy de SettingsView a español neutro (alineado a Setup/copy y
    al mockup ajustes.txt). Review nativo APROBADO.
  · WU5 (496d60e) capa "a prueba de tontos": catálogo OpenRouter (8 modelos,
    pago/gratis con precios), guías paso a paso + links directos, presets no
    OpenRouter en "Próximamente". Review NO completó (#4655, STATUS atado
    operation_timeout 3/3) → candidato SIN review, ocurrencia reportada.
  · B1 (e56e0aa) GATE PROVIDER-AWARE (D6): la whitelist curada deja de aplicarse a
    Groq/Ollama/LM Studio/Custom; solo OpenRouter y el fallback de entorno siguen
    gateados. Cierra el dead-end de WU5 y habilita los 5 presets. Review nativo
    APROBADO (`review-77efa93813d92957`) con 3 advisories (→ B6).
  · B2 (0d094b8) catálogo + guías más allá de OpenRouter: 3 modelos Groq reales
    con tarifa, guías por proveedor, y facilitación del paso Modelo (placeholder
    por proveedor, "Reintentar", dedupe de avisos, hint local). Review nativo
    APROBADO con 3 advisories.
  · B2-advisories (39aa921) pricing provider-aware: `_PROVIDER_SCOPED_RATES` con
    clave (provider, slug) para que un slug de Groq no se pricee a tarifa Groq
    bajo otro proveedor (desconocido → NULL, nunca un número equivocado);
    priceLabel hasta 3 decimales ($0.075). Mantenimiento del store de review:
    27 lineages huérfanas abandonadas → clean.
  · B3 (8325eab) hardening del probe: AbortController + timeout de 15s en el
    cliente para que el botón no quede clavado en "Comprobando…" (el server ya
    acotaba a 5s; el hueco era el abort del cliente). Verificación independiente
    pass_with_advisories.
  · B4 (b0940a6 + a6be79e) pulido chico: Ajustes muestra el copy español del
    rechazo SSRF en vez de "API error 422"; tarifa de
    meta-llama/llama-3.3-70b-instruct agregada al mapa (verificada en la fuente
    primaria de OpenRouter: $0.10/$0.32 por millón).
  · B6 (31017c5 + d6ae7ad + c1c2037) cierre de los advisories de B1: test de
    paridad entre el espejo del cliente (modelGate.ts) y _UNRESTRICTED_PROVIDERS
    del servidor (verificado inyectando un drift a propósito: el test falla y
    nombra ambos lados); caso restringido del gate (openrouter + modelo arbitrario
    → 422, y el modelo resuelto es el que se reenvía a build_provider); y
    normalización del provider_type guardado desconocido (higiene de estado: el
    síntoma que describía el advisory NO reproduce — RHF valida los radios desde
    el DOM). Suites: backend 739, web 512, build ✓; validado en vivo.
  REVIEWS NATIVAS: aprobadas en WU1/WU2/WU4/B1/B2; sin review en WU3 (sin
  receipt), WU5 (#4655), B2-advisories, B3, B4 y B6 → entrega por política
  ordinaria del repo. Próximo: la EXPLORACIÓN INICIAL de la sección PROFILE
  (definir cómo se configura: primero relevar, no implementar); el ROADMAP de
  Settings ya tiene su (1) HECHO —fusión, main @ 642fbe5— y le quedan el dashboard
  de uso/costos y los defaults de análisis. Suelto: B5 (deuda de review/proceso).

- 19/10 (sesión 22): **SECCIÓN PERFIL — PRIMERA ENTREGA**. Se hizo la exploración
  read-only que esta Ruta había dejado como próximo paso y, sobre ella, la primera
  entrega de la sección: `/app/profile` con card Cuenta (email SOLO LECTURA +
  cambio de contraseña) y card Sesión (cerrar sesión). Backend nuevo
  `POST /api/auth/password` (verifica la actual → 401; rechaza <8 caracteres →
  422; re-hashea y BORRA LAS DEMÁS SESIONES dejando viva la del que cambia → 204)
  + `update_user_password` y `delete_other_auth_sessions` en el store. Frontend:
  `ProfileView`, `ChangePasswordDialog` (focus trap; Escape/Cancelar no mandan
  nada), `useChangePassword` y el helper puro `displayNameFromEmail`; el bloque
  de usuario del sidebar pasó a avatar + nombre derivado del email + link al
  perfil, y perdió el botón "Log out" (el logout vive en la card Sesión).
  CUATRO DECISIONES DE PRODUCTO cerradas con el maintainer: (a) nombre derivado
  del email y editable DESPUÉS (anotado en el pulido de registro); (b) correo
  solo lectura; (c) cambiar contraseña cierra las demás sesiones y deja la
  actual; (d) modernizar SOLO el bloque de usuario del sidebar (el resto del
  shell queda para otra obra — ver el inventario huérfano). Evidencia: backend
  **752 passed**, web **546 passed** + `npm run build` ✓, focalizado de auth
  **80 passed**; verificador independiente (riesgo ítem 2, credenciales)
  **S4 PASS / S8 PASS** con MUTACIONES inyectadas en copias de /tmp (comentar la
  purga hace fallar el test; saltear el update también; sin el filtro
  `token_hash != ?` fallan 3 tests del store); diferencial de logout/me idéntico
  contra el base; validación EN VIVO del maintainer OK. Commits en main:
  `7f8b635` (backend, aislado para que un review pueda tomarlo solo) + `711cf2a`
  (frontend + shell). Ficha: `odd/tasks/profile-section.md` (S1-S8, D1-D4,
  L1-L11). Aprendizajes de proceso: el harness de subagentes usa
  `/tmp/gpK4cT14` como raíz de `mkdtemp` — BORRARLO rompe el arranque de los
  writers (pasó y se resolvió recreándolo); y `gentle_review assess` pre-commit
  devuelve `nativeRisk: unassessable` porque los archivos sin trackear exigen
  una declaración explícita. Próximo: DISCUTIR las funciones del perfil en tres
  capas (principales / secundarias de UX-calidad de vida / innovadoras), sin
  escribir código; después, el pulido de login/registro con el campo de nombre.

- 19/10 (sesión 23): **SECCIÓN PERFIL — FUNCIONES DECIDIDAS** (charla de
  producto, SIN escribir una línea de código). El maintainer trajo las tres capas
  —la lista trabajada con Claude: principales (cambio de email con verificación,
  gracia en el borrado, aviso de nuevo inicio de sesión), UX/calidad de vida
  (avatar real, historial de actividad, export de datos) e innovadoras (panel de
  consumo en el Perfil, resumen tipo "wrapped")— y el orquestador la contrastó
  contra el código ANTES de planificar. Resultado: **7 obras** en orden de
  **COMPLEJIDAD DESCENDENTE** (T7 → T3 → T2 → T6 → T5 → T4 → T1), con migraciones
  previstas 0006 (users.name), 0007 (auth_sessions: user_agent ~120 sin IP +
  last_seen_at real) y 0008 (users.pending_deletion_at). Ficha nueva:
  `odd/tasks/profile-roadmap.md` (S1-S10, D1-D8, L1-L9); `odd/` sigue untracked
  por `.git/info/exclude`, cero cambios en archivos versionados.
  DOS PREMISAS EXTERNAS CAYERON AL VERIFICARLAS: "en Files hay delete duro sin
  confirmación y ahí se decidió que la confirmación no alcanza" es FALSO
  (`web/src/routes/FilesView.tsx:348` usa `ConfirmDialog` y la ficha
  files-f4-delete-confirm.md existe justamente para eso), y "el aviso de nuevo
  login es solo dispararlo" es FALSO (no hay NINGUNA infra de correo en el repo:
  el grep de smtp|sendgrid|mail sobre server/ solo devuelve la palabra "email").
  PREMISAS CIERTAS: el gap de pantalla de uso/costos ya estaba anotado
  (`odd/tasks/settings-production-readiness.md:95` y `:416`) y el export de
  Archive a Markdown existe pero es client-side y de a uno
  (`web/src/lib/archiveMarkdown.ts`, `ArchiveList.tsx:385-387`).
  HALLAZGOS DEL RELEVAMIENTO: `auth_sessions.last_seen_at` EXISTE pero NADIE la
  escribe (hoy la tabla solo se lee, `server/services/sqlite_store.py:171-186`),
  así que "última actividad" exige una escritura en el camino caliente de CADA
  request autenticado — eso es lo que hace a T2 más pesada de lo que parece;
  borrar la cuenta se lleva también `user_settings.api_key_enc` (la API key
  cifrada del proveedor, `SecretBox.for_store`), algo que el copy del diálogo
  debe avisar; y `users.id` es AUTOINCREMENT, o sea que un `rmtree` fallido deja
  espacio huérfano pero NUNCA datos heredados por otro usuario.
  DECISIONES DE PRODUCTO CERRADAS: nombre editable AHORA dentro del Perfil (no en
  el pulido de registro); sesiones con navegador + última actividad real; borrado
  con las dos llaves (texto ELIMINAR + contraseña actual) y GRACIA DE 7 DÍAS
  cancelable, purgada desde el barrido horario que ya existe
  (`server/api/main.py:34-48`); aviso de sesión nueva DENTRO de la app (sin
  correo, que queda como deuda por dependencia externa); entran panel de consumo,
  export de la cuenta y bitácora personal; y el repintado va con **PERFIL como
  piloto** y alojando las preferencias (Ajustes queda con LLM y modelo). El
  AVATAR fue ofrecido y NO fue seleccionado. Corregido además el razonamiento
  anterior que ponía el repintado al final "para no repintar dos veces": va al
  revés — si T7 va primero, las obras funcionales nacen ya en el sistema nuevo.
  PRÓXIMO: T7 (repintado + preferencias), arrancando por su RONDA DE ALCANCE;
  queda abierto si T7 se parte en dos (T7a sistema de diseño + Perfil piloto /
  T7b resto de las pantallas + preferencias) para no bloquear las seis obras
  funcionales detrás.

- 26/10 (sesión 24): **T7a PREFERENCIAS DEL PERFIL — ENTREGADA Y PUSHEADA** +
  **FIX DE LAYOUT DEL CHAT**. Ronda de alcance de T7: el maintainer preguntó qué
  era el "repintado" y aclaró su método ("primero funcionalidad y luego cirugía
  plástica") → T7 se PARTIÓ en **T7a preferencias** (funcional) y **T7b repintado
  Dark Cockpit** (cosmético, ÚLTIMO), y el orden pasó a
  T7a → T3 → T2 → T6 → T5 → T4 → T1 → T7b. Decisiones de producto:
  números es/internacional; fechas relativa/absoluta (solo timestamps de la app,
  nunca fechas dentro de un dataset); moneda = solo el SÍMBOLO del costo de Datara
  (que es USD: SIN conversión); comportamiento al abrir; dark como tema ÚNICO (sin
  toggle). ENTREGADO: migración 0006 (4 columnas nullable en user_settings),
  módulo de preferencias con defaults que reproducen el comportamiento previo,
  GET/PUT /api/settings, card Preferencias en Perfil con botón Restablecer,
  formatters con preferencia, y el formato inyectado en CADA llamada del chat
  (prompt principal, reparación, segunda pasada y post-procesador de números).
  El prompt por defecto quedó BYTE-IDÉNTICO (su test de SHA-256 intacto).
  Verificación: backend 788, web 569, build ✓; verificador independiente con
  TODOS los ítems PASS (que además cazó una carrera de AppLanding con
  open_behavior=last_session, arreglada con test; y se sumaron los tests
  cosechados de sus probes: migración, invariantes del 422 atómico y render con
  preferencia en componentes reales); validación EN VIVO del maintainer (fechas y
  botón Restablecer confirmados). Commits `a4d602d` (backend) + `610b1bc` (chat) +
  `8f91759` (frontend). REVIEW NATIVO: el START sobre /mnt/c falló con
  `candidate-view checkout-index timeout` (10 s, defecto de 9p ya reportado,
  lineage_created=false); el workaround acordado FUNCIONÓ — clon en ext4
  (/home/danieldlrt09/datara-review) → el START materializó y devolvió el envelope
  de consentimiento (medium, 25 archivos, 1754 líneas) → el maintainer eligió
  "Skip this time" (`declined_this_candidate`): candidato SIN review por decisión
  explícita, con verificador independiente + validación en vivo como evidencia.
  FIX DE LAYOUT (commit propio `fcb2047`, ajeno a T7a): el chat quedaba más ancho
  que la ventana (scroll horizontal permanente, tablas cortadas), reportado por el
  maintainer como "se agranda de la nada" y probado que NO era zoom (a 100%
  seguía). Causa: la columna del chat (`web/src/routes/ChatView.tsx`, `flex: 1`
  sin `minWidth: 0`) no podía encogerse por debajo del contenido, y un gráfico de
  plotly conservaba un ancho en píxeles medido al dibujarse (su `responsive` solo
  escucha el resize de la ventana). Fix: `minWidth: 0` en la columna,
  `overflow: hidden` en el contenedor del gráfico y re-ajuste por
  `ResizeObserver` con guarda anti-loop; test-first (2 tests nuevos del chart).
  Push `21bcd25..fcb2047` a `origin/main` por decisión explícita del maintainer.
  Deudas anotadas: dos avisos cosméticos del verificador (el `null` explícito en
  el PUT es no-op, como el resto de Ajustes; quedó un `formatTableValue` viejo sin
  uso) y AGENTS.md desactualizado (dice ~357/~88; hoy 788/569).

- 29-30/10 (sesiones 25-28, reconstruidas del historial de git — este archivo
  quedó sin actualizar entre el 26/10 y el 03/11): **PERFIL COMPLETADO ENTERO
  (T5 → T4 → T6 → T1) + PULIDO DEL REGISTRO COMPLETO (seguridad, experiencia,
  términos de uso)**. Orden entregado: **T5 bitácora personal** (`f59c293`
  endpoint + `9c6b779` UI); **T4 export de la cuenta** (`3b5ac24` zip streaming
  server-side + `1e0a72f` botón en Perfil); **T6 panel de consumo** (`d6e9fa5`
  consumo mensual por usuario + `ab1a464` card en Perfil); **T1 nombre editable**
  (`42c53cc` migración 0009 + `4a3a681` fila Nombre en Perfil); **seguridad de
  auth** (`edaf816` email case-insensitive, `f5b403d` rechazo de email mal formado,
  `e8858fb`+`8ba503f` freno de intentos y su mensaje, `f2c199f` tests de identidad
  y tope, `2c514b8` cierre de los hallazgos de rate-limit/timing, `ea73ef6` test
  del dummy login); **experiencia del registro** (`b7ec67b` nombre opcional en el
  alta + `74458f9` pantalla del alta pulida: labels, copy ES, repetir contraseña,
  medidor de fuerza informativo); **términos de uso** (`d64e0b1` texto ES/EN 1.0,
  `23c89bc` migración 0011 + registro de la aceptación, `df0442c` página
  `/terminos` + casillero obligatorio en el alta, `0b42846` correo de contacto).
  `main` @ 207879c (incluye `2682312` y `207879c` refrescando los conteos de
  tests en `AGENTS.md`).

- 03/11 (sesión 29): **VERIFICACIÓN DE CORREO + RECUPERACIÓN DE CONTRASEÑA —
  ENTREGADAS, PUSHEADAS Y MERGEADAS A `main` (PR #22, `7300598`)** + **HALLAZGO Y FIX DEL
  LOGGING**. Se retomó la obra `email-verification-recovery` (implementada pero sin
  commitear) y se cortó en 6 work units: `476b9eb` (mailer: protocolo `Mailer` con
  `SmtpMailer` real y `ConsoleMailer` de desarrollo), `e892f07` (migración 0012:
  `users.email_verified_at` + tabla `auth_tokens` de un solo uso guardando solo el
  hash), `f0e1e53` (endpoints: `register` ya NO abre sesión, `login` 403 si el
  correo no está verificado, y `verify-email`/`resend-verification`/
  `forgot-password`/`reset-password` no enumerantes), `2ad7efc` (adaptación de 31
  suites al contrato nuevo), `18038e3` (frontend: 4 pantallas + hooks + links) y
  `feab8bf` (fix del logging). **GATE DURO**: sin verificar no se entra (registro →
  "revisá tu correo" → link → verificado → login). Expiraciones: verificación 24 h,
  recuperación 1 h; un reset también marca el correo como verificado y mata todas
  las sesiones. Suites: backend **1044 passed** (el único fallo fue un flake de
  sandbox en 9p, confirmado ambiental por verificador independiente: 3/3 aisladas)
  y web **692 passed** (65 archivos), `npm run build` ✓.
  REVIEW NATIVO desde el clon ext4 `/home/danieldlrt09/datara-review-ev`, un lineage
  por corte riesgoso: `review-15ebe09994ede13a` (storage) y
  `review-11835031fcdf5830` (endpoints), **APROBADOS Y QUEMADOS**, 27 hallazgos
  todos informativos (ninguno abrió corrección). Los cuatro cortes restantes
  quedaron SIN review por **decisión explícita del maintainer** (waiver
  registrado en la ficha). Aprendido: el candidato es `baseRef..HEAD` (hay que
  parar el clon en el commit del corte) y la receta de admisión parcial (un STATUS
  fresco reofrece el slot rechazado; nunca reenviar los bytes rechazados).
  HALLAZGO DEL LOGGING, destapado por la **validación en vivo** y no por los tests:
  ningún módulo configuraba logging, así que los `logger.info` de la app caían al
  logger raíz (sin handlers, nivel WARNING) y **se descartaban en silencio** — el
  `ConsoleMailer`, cuyo único trabajo es entregar el link, no imprimía nada, y el
  link no era recuperable (la base guarda solo el hash del token). Fix:
  `server/logging_setup.py` + llamada en el lifespan (no-op si el host ya tiene
  handlers), con test propio (RED→GREEN) y diferencial de arranque.
  ENTREGA REAL VALIDADA EN VIVO: primero contra un catcher SMTP local (el
  `SmtpMailer` nunca había ejecutado: los tests usan un `smtplib` falso) y después
  contra Gmail real (587/STARTTLS con contraseña de aplicación) — el maintainer
  confirmó que los correos llegaron a su casilla; el registro de prueba dio 200
  **sin cookies** (el gate se cumple). `main` @ 207879c; rama
  `feat/email-verification-recovery` pusheada a `origin`; ficha
  `odd/tasks/email-verification-recovery.md`. **PRÓXIMO: T7b (repintado Dark
  Cockpit)** y decidir el merge de la rama del correo. Deuda anotada: los 27
  hallazgos informativos, el aviso de arranque cuando el cartero cae a consola, el
  cambio de correo con verificación (S6) y dos líneas para bajar el ruido de
  `httpx`/`openai` en el log.

- 03/11 (segunda parte, sesión 29): **DECISIONES DEL REWORK — DATARA PASA A
  SER UN EJECUTABLE DE ESCRITORIO** (el maintainer lo resumió así: *"Siento
  que este es el verdadero rework de datara"*). Salió de la pregunta de
  arquitectura "¿cambiaría algo si Datara fuera un .exe?" y de medir el
  hardware real. Decisiones: (1) **proveedores en la nube**, modelos
  **locales descartados** (16 GB de RAM y 4 GB de VRAM dan techo en 7-8B, y
  no se puede asumir máquinas potentes en los analistas); (2) forma:
  **ejecutable primero en VENTANA PROPIA**, página hospedada quizá después;
  (3) **identidad local** (perfil + bloqueo opcional) con las pantallas de
  correo **ocultas** pero conservadas para el hospedado; (4) primer arranque
  **estilo tutorial con animación del logo**; (5) **privacidad declarada**
  (niveles por archivo/sesión + visor de lo que se envía) en lugar de la
  promesa imposible de "nada sale": el archivo crudo nunca sale, el cálculo
  es local, sale esquema + muestras acotadas + los valores de las tablas ya
  calculadas, y **la data va del analista a su proveedor con su clave, nunca
  por servidores de Datara**; (6) el camino corporativo serio es apuntar
  Datara al **endpoint de la empresa** (Azure/Bedrock/vLLM interno), que no
  necesita hardware del analista. Se sumó el **bloque de funcionalidad
  pre-repintado** (sección propia más arriba) con nueve tareas F1-F9, y el
  repintado T7b pasó a **ÚLTIMO** con la regla del maintainer: *"sigamos en
  funcionalidad y nada de cirugía plástica hasta que la funcionalidad esté
  lista"*. Documentos actualizados: esta Ruta y `Datara 2 - Objetivos del
  proyecto.txt`. Limpieza: se borraron los cuatro `datara-validaciones*` del
  Escritorio (backup en `/tmp/datara-validaciones-backup-20261103-1748/`).

─────────────────────────────────────────────
SECCIÓN ANÁLISIS (Archives) — ✓ CERRADA (A1→A4), PASO A PASO
─────────────────────────────────────────────
Estado HOY: ✓ CERRADA (02/10, sesión 21): A1 ✓ backend; A2 ✓ crear desde el chat; A3 ✓ UI de la lista; A4 ✓ ciclo de vida y semántica Reabrir/Exportar.
Backend (e3baa31, época scaffold, +0005 en A1) con
POST /api/archives, GET /api/archives y GET /api/archives/{id}, per-user,
SIN delete/restore/rename ni paginación; un archive = snapshot JSON de una
sesión (session + messages + metadata de files). Frontend: A2 (sesión 19)
cableó useCreateArchive con el botón «Guardar análisis» del composer; ahora sí
se crea desde la UI. A3 (sesión 20) reconstruyó web/src/routes/ArchiveList.tsx
(búsqueda, orden, tarjetas, detalle lazy) y el endpoint de lista deriva el
metadata de cada tarjeta. Diseño de referencia:
Pantallas/archives/analisis.txt + Pantallas/DESIGN.md:215-237.
Decisión del usuario (01/10/2026, sesión 17): trabajarlo PASO A PASO, un
ítem por sesión (A1 → A4); NO abrir SDD.

Defectos de fondo verificados (resueltos en A1):
1. archives.chat_session ... ON DELETE CASCADE (0001_init.sql:86): borrar
   la sesión borra sus análisis → contradice "guardar para reabrirlo
   después". Migración: ON DELETE SET NULL + chat_session nullable.
2. Snapshot invertido y truncado: archive.py:68 usa
   list_messages(limit=500), que ordena created_at DESC, id DESC
   (sqlite_store.py:372) → guarda los mensajes al revés y corta a los
   últimos 500.
3. Sin índice archives(user_id, created_at); sin paginación; name y
   payload_json sin cap.

Plan por sesión:
- A1 (✓ CERRADO 01/10, sesión 18; commit 70cc276 pusheado a main)
  FUNDACIONES BACKEND: migración 0005 (rebuild de tabla → chat_session
  nullable + ON DELETE SET NULL, user_id sigue CASCADE, preserva filas/ids)
  + índice idx_archives_user_created(user_id, created_at); snapshot ASC y
  completo (limit=None) con message_count/truncated; caps de name (200 →
  422) y payload (8 MiB → 413); schemas toleran chat_session null.
  Backend-only, con tests (30 focused / 681 full verdes); verificador
  independiente PASS WITH FINDINGS (0 BLOCKER); live sobre copia de la DB
  real OK. RDD no completable (transport #4030) → el usuario eligió "Seguir
  sin reportar" → candidato sin revisión, entrega por política normal.
- A2 (✓ CERRADO 02/10, sesión 19; commit e3d6901 pusheado a main)
  CREAR DESDE CHAT: botón «Guardar análisis» en el composer (al lado de
  «Adjuntar») + diálogo `SaveAnalysisDialog` (nombre precargado con el título
  de la sesión). Gates, mapeo de errores (413/422/404/genérico) y aviso de
  éxito con link a /app/archives. Web 420/420, build ✓; verificador
  independiente PASS; validación EN VIVO OK. RDD no completable (transport
  #4030) → "Seguir sin reportar".
- A3 (✓ CERRADO 02/10, sesión 20; commit 0c4d9a8 pusheado a main)
  UI ANÁLISIS: ArchiveList reconstruida — búsqueda ("Buscar análisis…"), orden
  «Más recientes»/«Más antiguos», tarjetas con título + chip de archivo (+N) +
  tiempo relativo + resumen «N filas · M columnas» + Reabrir/Exportar inertes
  (semántica en A4), copy español neutro (sin voseo), payload lazy al expandir
  (N+1 eliminado). El chip de estado se OMITE: no existe concepto ni fuente.
  Backend mínimo: files/row_count/column_count derivados del snapshot con
  parser guardado. Web 433, archive focused 25, build ✓; verificador
  independiente halló el CRÍTICO del link /app → 404 → corrección →
  re-verificación PASS; validación EN VIVO OK. RDD no completable
  (operation_timeout nativo, distinto del #4030) → "Continuar sin reportar".
- A4 (✓ CERRADO 02/10, sesión 21; commits cb6c5e9 + e0d2d14 pusheados a main)
  CICLO DE VIDA COMPLETO. Decisiones de producto resueltas al abrir A4:
  Reabrir = «sesión viva, fallback a snapshot» (si chat_session existe navega
  a /app/chat/{id} para seguir conversando; si la sesión fue borrada y quedó
  NULL, abre el snapshot en modo LECTURA sin tocar sesión viva); Exportar =
  «Markdown del snapshot completo», 100% client-side (PDF/HTML queda en Fase 3).
  Backend (cb6c5e9): list_archives con keyset keyword-only (limit/before_id,
  ORDER BY created_at DESC, id DESC); delete_archive; rename_archive; router
  DELETE 204/404, PATCH → ArchiveListItem con _validate_archive_name
  compartido, GET paginado (limit 1..200 default 50, before), _load_payload
  guarda los json.loads (cierra el menor pre-existente). Frontend (e0d2d14):
  useArchives → useInfiniteQuery (page 50, «Cargar más»); useDeleteArchive /
  useRenameArchive; nuevo lib/archiveMarkdown.ts (serializador puro + download)
  y components/ArchiveSnapshot.tsx (reusa ChatMessage en modo read-only);
  ArchiveList con Reabrir/Exportar/Renombrar/Borrar (ConfirmDialog) y el
  JSON crudo reemplazado por el snapshot legible. Suite: backend 709, web 459,
  build ✓. Verificador independiente adversarial PASS WITH FINDINGS (2
  WARNINGs de tests que no discriminaban) → corrección → re-verificación
  (4/5 cerrados; el test del tiebreaker quedó documental por el índice inverso,
  docstring honesto). RDD nativo: envelope de consentimiento relayado, el
  usuario eligió «Saltear esta vez» (declined_this_candidate) → candidato sin
  revisión, entrega por política ordinaria. Validación EN VIVO OK.
  Limitación conocida: búsqueda/orden client-side sobre las páginas cargadas
  (avisada en la UI).

Independiente de A1-A4 — backlog post-salida de Files (observabilidad
primero, luego containment del delete y el resto): ver
odd/tasks/files-post-launch-hardening.md.

Notas:
- La planificación SDD detallada vive en memoria persistente
  (engram, proyecto `datara-2` — la key con espacio se consolidó el 11/09).
- Los cambios de feature grande entran por SDD
  (/sdd-new o /sdd-ff), no directo a código.
