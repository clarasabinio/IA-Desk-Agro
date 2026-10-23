from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


class Campo(models.Model):
    """
    Establecimiento o campo general (ej: Campo La Esperanza, Campo El Ombú).
    """
    nombre = models.CharField(max_length=150, unique=True, verbose_name="Nombre del Establecimiento")
    ubicacion = models.CharField(max_length=250, blank=True, null=True, verbose_name="Ubicación / Localidad")
    superficie_total_ha = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal("0.00"), 
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Superficie Total (ha)"
    )
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción / Instalaciones")

    class Meta:
        verbose_name = "Campo / Establecimiento"
        verbose_name_plural = "Campos / Establecimientos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.superficie_total_ha} ha)"


class Lote(models.Model):
    """
    Lote o parcela física de laboreo agrícola dentro de un campo.
    """
    campo = models.ForeignKey(
        Campo,
        on_delete=models.CASCADE,
        related_name="lotes",
        verbose_name="Campo Perteneciente",
        null=True,
        blank=True
    )
    nombre = models.CharField(max_length=100, verbose_name="Identificador del Lote (ej: Lote 1, Lote Norte)")
    superficie_ha = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.10"))],
        verbose_name="Superficie Agrícola (ha)"
    )
    tipo_suelo = models.CharField(max_length=150, blank=True, null=True, verbose_name="Tipo de Suelo / Serie")
    activo = models.BooleanField(default=True, verbose_name="Lote Activo en Producción")

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        ordering = ["campo", "nombre"]
        unique_together = [("campo", "nombre")]

    def __str__(self):
        campo_str = f" - {self.campo.nombre}" if self.campo else ""
        return f"{self.nombre}{campo_str} ({self.superficie_ha} ha)"


class CicloCultivo(models.Model):
    """
    Campaña agrícola o ciclo productivo asignado a un lote.
    """
    CULTIVOS_CHOICES = [
        ("soja_primera", "Soja de 1ra"),
        ("soja_segunda", "Soja de 2da"),
        ("maiz", "Maíz Grano Comercial"),
        ("trigo", "Trigo Pan"),
        ("girasol", "Girasol"),
        ("sorgo", "Sorgo"),
        ("cebada", "Cebada"),
        ("otro", "Otro Cultivo / Barbecho"),
    ]

    ESTADO_CHOICES = [
        ("planificado", "Planificado / Barbecho"),
        ("siembra", "En Siembra"),
        ("crecimiento", "En Crecimiento Vegetativo / Reproductivo"),
        ("cosechado", "Cosechado / Finalizado"),
    ]

    lote = models.ForeignKey(
        Lote,
        on_delete=models.CASCADE,
        related_name="ciclos_cultivo",
        verbose_name="Lote Asignado"
    )
    campana = models.CharField(
        max_length=50,
        default="2026/2027",
        verbose_name="Campaña Agrícola (ej: 2026/2027)"
    )
    cultivo = models.CharField(
        max_length=50,
        choices=CULTIVOS_CHOICES,
        default="soja_primera",
        verbose_name="Cultivo Sembrado"
    )
    variedad_hibrido = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Variedad o Híbrido (ej: DM 46R18 / DK 72-10)"
    )
    fecha_siembra = models.DateField(blank=True, null=True, verbose_name="Fecha de Siembra")
    fecha_cosecha = models.DateField(blank=True, null=True, verbose_name="Fecha de Cosecha")
    estado = models.CharField(
        max_length=30,
        choices=ESTADO_CHOICES,
        default="crecimiento",
        verbose_name="Estado Fenológico / Operativo"
    )
    rinde_esperado_qq_ha = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Rinde Objetivo (qq/ha)"
    )
    rinde_obtenido_qq_ha = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Rinde Final Obtenido (qq/ha)"
    )

    class Meta:
        verbose_name = "Ciclo de Cultivo"
        verbose_name_plural = "Ciclos de Cultivo"
        ordering = ["-campana", "lote", "cultivo"]

    def __str__(self):
        return f"{self.campana} | {self.get_cultivo_display()} en {self.lote.nombre} ({self.variedad_hibrido or 'S/D'})"


class Deposito(models.Model):
    """
    Depósito físico o punto de almacenamiento: Cisternas, tanques móviles, silos, galpones o acopio externo.
    """
    TIPO_CHOICES = [
        ("cisterna", "Cisterna Fija"),
        ("tanque_movil", "Tanque Móvil de Campo"),
        ("acopio_externo", "Acopio en Proveedor / Distribuidor"),
        ("galpon", "Galpón de Insumos"),
        ("silo", "Silo de Granos"),
    ]

    codigo = models.SlugField(max_length=50, unique=True, verbose_name="Código Interno (Slug)")
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Depósito / Tanque")
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default="cisterna", verbose_name="Tipo de Depósito")
    capacidad_maxima = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Capacidad Máxima"
    )
    stock_actual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Stock Físico Actual"
    )
    unidad_medida = models.CharField(max_length=30, default="litros", verbose_name="Unidad de Medida")
    campo = models.ForeignKey(
        Campo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depositos",
        verbose_name="Establecimiento / Ubicación"
    )
    descripcion = models.CharField(max_length=250, blank=True, null=True, verbose_name="Detalle de Ubicación / Estado")
    activo = models.BooleanField(default=True, verbose_name="Operativo / Activo")

    class Meta:
        verbose_name = "Depósito / Tanque"
        verbose_name_plural = "Depósitos y Tanques"
        ordering = ["tipo", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.stock_actual:,.0f} / {self.capacidad_maxima:,.0f} {self.unidad_medida})"

    @property
    def porcentaje_llenado(self) -> float:
        if self.capacidad_maxima > 0:
            return round(float(self.stock_actual / self.capacidad_maxima) * 100, 1)
        return 0.0

    @property
    def espacio_disponible(self) -> Decimal:
        return max(Decimal("0.00"), self.capacidad_maxima - self.stock_actual)


class Insumo(models.Model):
    """
    Catálogo de insumos agrícolas: Gasoil, semillas, fertilizantes, fitosanitarios.
    Diferencia stock físico en campo, stock por retirar (acopio) y stock comprometido/reservado.
    """
    CATEGORIA_CHOICES = [
        ("combustible", "Combustible (Gasoil / Diesel)"),
        ("semilla", "Semilla Fiscalizada"),
        ("fertilizante", "Fertilizante"),
        ("fitosanitario", "Fitosanitario / Agroquímico"),
        ("otro", "Otro Insumo"),
    ]

    UNIDAD_CHOICES = [
        ("litros", "Litros (L)"),
        ("bolsas", "Bolsas (u)"),
        ("kilogramos", "Kilogramos (kg)"),
        ("toneladas", "Toneladas (Tn)"),
    ]

    nombre = models.CharField(max_length=150, verbose_name="Nombre del Insumo / Producto")
    categoria = models.CharField(max_length=40, choices=CATEGORIA_CHOICES, verbose_name="Categoría")
    unidad_medida = models.CharField(max_length=30, choices=UNIDAD_CHOICES, default="litros", verbose_name="Unidad de Medida")
    
    # SALDOS DISGREGADOS POR CONDICIÓN DE DISPONIBILIDAD
    stock_actual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Stock Físico en Campo (Disponible)"
    )
    stock_por_retirar = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Stock por Retirar / Acopio Externo"
    )
    stock_reservado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Stock Comprometido / Reservado"
    )
    stock_minimo_alerta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Stock Mínimo de Alerta"
    )
    deposito_habitual = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Depósito Principal (ej: Cisterna, Tanque Grande, Galpón 1)"
    )

    class Meta:
        verbose_name = "Insumo / Producto"
        verbose_name_plural = "Insumos y Productos"
        ordering = ["categoria", "nombre"]

    def __str__(self):
        return f"[{self.get_categoria_display()}] {self.nombre} ({self.stock_actual} {self.unidad_medida})"

    @property
    def stock_total_general(self) -> Decimal:
        return self.stock_actual + self.stock_por_retirar

    @property
    def esta_bajo_minimo(self) -> bool:
        return self.stock_minimo_alerta > 0 and self.stock_actual <= self.stock_minimo_alerta


class MovimientoStock(models.Model):
    """
    Registro histórico y contable de entradas, traslados y consumos de insumos.
    Auditable, con soporte para idempotencia, saldos antes/después y trazabilidad de lotes.
    """
    TIPO_CHOICES = [
        ("consumo_labor", "Consumo en Labor Agrícola"),
        ("ingreso_compra", "Ingreso por Compra / Remito"),
        ("traslado_interno", "Traslado entre Depósitos"),
        ("ajuste_inventario", "Ajuste de Inventario / Conteo Físico"),
        ("retiro_acopio", "Retiro desde Acopio Proveedor"),
    ]

    ESTADO_CHOICES = [
        ("confirmado", "Confirmado y Asentado"),
        ("pendiente", "Pendiente de Confirmación"),
        ("anulado", "Anulado / Corregido"),
    ]

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.PROTECT,
        related_name="movimientos",
        verbose_name="Insumo Afectado"
    )
    tipo_movimiento = models.CharField(
        max_length=40,
        choices=TIPO_CHOICES,
        default="consumo_labor",
        verbose_name="Tipo de Movimiento",
        db_index=True
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="confirmado",
        db_index=True,
        verbose_name="Estado del Registro"
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Cantidad Afectada"
    )
    fecha = models.DateField(default=timezone.now, db_index=True, verbose_name="Fecha del Movimiento")

    # CLAVES FORÁNEAS OPCIONALES A LOTES Y CICLOS DE CULTIVO
    lote = models.ForeignKey(
        Lote,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_stock",
        verbose_name="Lote Destino",
        help_text="Opcional. Seleccionar si el consumo corresponde a una labor en un lote particular."
    )
    ciclo_cultivo = models.ForeignKey(
        CicloCultivo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_stock",
        verbose_name="Ciclo de Cultivo / Campaña",
        help_text="Opcional. Vincular a la campaña o cultivo específico del lote."
    )

    # VINCULACIÓN A DEPÓSITOS (ORIGEN Y DESTINO PARA TRASLADOS)
    deposito_origen_fk = models.ForeignKey(
        Deposito,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salidas",
        verbose_name="Depósito Origen"
    )
    deposito_destino_fk = models.ForeignKey(
        Deposito,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entradas",
        verbose_name="Depósito Destino (Traslados/Ingresos)"
    )

    # TRAZABILIDAD OPERATIVA
    labor_realizada = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Labor Realizada (ej: Siembra, Pulverización, Disco)"
    )
    maquinaria = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Maquinaria Utilizada"
    )
    operario = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Operario / Tractorista a Cargo"
    )
    deposito_origen = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Texto Depósito Origen (Legacy / Fallback)"
    )
    documento_referencia = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Nro. Remito / Factura / Orden de Trabajo"
    )

    # TRAZABILIDAD DE SALDOS ANTES Y DESPUÉS
    saldo_anterior = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Saldo Previo en Depósito"
    )
    saldo_posterior = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Saldo Resultante en Depósito"
    )

    # IDEMPOTENCIA PARA EVITAR DOBLE REGISTRO POR DOBLE CLIC
    idempotency_token = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        verbose_name="Token de Idempotencia"
    )

    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones / Justificación")
    creado_el = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora de Creación")

    class Meta:
        verbose_name = "Movimiento de Stock"
        verbose_name_plural = "Movimientos de Stock"
        ordering = ["-fecha", "-creado_el"]

    def __str__(self):
        destino = f" -> {self.lote.nombre}" if self.lote else ""
        return f"{self.fecha} | {self.get_tipo_movimiento_display()} ({self.cantidad} {self.insumo.unidad_medida} {self.insumo.nombre}){destino}"
