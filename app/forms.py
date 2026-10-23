from django import forms
from django.db import transaction
from .models import MovimientoStock, Lote, CicloCultivo, Insumo


class ConsumoInsumoForm(forms.ModelForm):
    """
    Formulario especializado para asentar consumos de insumos en labores agrícolas.
    Facilita la selección clara del Lote y Ciclo de Cultivo sin obligatoriedad rígida.
    """
    class Meta:
        model = MovimientoStock
        fields = [
            "insumo",
            "cantidad",
            "fecha",
            "lote",
            "ciclo_cultivo",
            "labor_realizada",
            "maquinaria",
            "operario",
            "deposito_origen",
            "observaciones"
        ]
        widgets = {
            "insumo": forms.Select(attrs={
                "class": "form-select input-agro",
                "placeholder": "Seleccione el insumo utilizado"
            }),
            "cantidad": forms.NumberInput(attrs={
                "class": "form-control input-agro",
                "step": "0.1",
                "placeholder": "Ej: 240.0"
            }),
            "fecha": forms.DateInput(attrs={
                "class": "form-control input-agro",
                "type": "date"
            }),
            "lote": forms.Select(attrs={
                "class": "form-select input-agro select-lote",
                "data-placeholder": "Seleccionar Lote de Destino"
            }),
            "ciclo_cultivo": forms.Select(attrs={
                "class": "form-select input-agro select-ciclo",
                "data-placeholder": "Vincular a Campaña / Cultivo"
            }),
            "labor_realizada": forms.TextInput(attrs={
                "class": "form-control input-agro",
                "placeholder": "Ej: Siembra Maíz / Pasada de Disco / Barbecho Químico",
                "autocorrect": "off",
                "spellcheck": "false"
            }),
            "maquinaria": forms.TextInput(attrs={
                "class": "form-control input-agro",
                "placeholder": "Ej: Tractor JD 7200R + Sembradora Crucianelli 27L",
                "autocorrect": "off",
                "spellcheck": "false"
            }),
            "operario": forms.TextInput(attrs={
                "class": "form-control input-agro",
                "placeholder": "Nombre del tractorista u operario",
                "autocorrect": "off",
                "spellcheck": "false"
            }),
            "deposito_origen": forms.TextInput(attrs={
                "class": "form-control input-agro",
                "placeholder": "Ej: Tanque Chico / Cisterna Planta / Galpón Central",
                "autocorrect": "off",
                "spellcheck": "false"
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control input-agro",
                "rows": 2,
                "placeholder": "Notas adicionales de la labor...",
                "autocorrect": "off",
                "spellcheck": "false"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 1. Filtro claro y amigable para seleccionar Lote
        self.fields["lote"].queryset = Lote.objects.filter(activo=True).select_related("campo").order_by("campo__nombre", "nombre")
        self.fields["lote"].empty_label = "-- 📍 Seleccionar Lote (Opcional si es gasto general) --"
        self.fields["lote"].required = False

        # 2. Filtro de Ciclos de Cultivo
        self.fields["ciclo_cultivo"].queryset = CicloCultivo.objects.select_related("lote").order_by("-campana", "lote__nombre")
        self.fields["ciclo_cultivo"].empty_label = "-- 🌾 Vincular a Cultivo / Campaña (Opcional) --"
        self.fields["ciclo_cultivo"].required = False

        # 3. Personalizar presentación del Insumo
        self.fields["insumo"].empty_label = "-- 📦 Seleccione el Insumo a Descontar --"

    def clean(self):
        cleaned_data = super().clean()
        insumo = cleaned_data.get("insumo")
        cantidad = cleaned_data.get("cantidad")

        if insumo and cantidad:
            if insumo.stock_actual < cantidad:
                # Advertencia técnica sin bloquear la operación si se desea permitir stock negativo temporal
                self.add_error("cantidad", f"Atención: El stock actual disponible de {insumo.nombre} es de {insumo.stock_actual} {insumo.unidad_medida}. La cantidad solicitada ({cantidad}) supera la existencia en depósito.")
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        """
        Al guardar el consumo, descuenta automáticamente la cantidad del stock del Insumo.
        """
        movimiento = super().save(commit=False)
        movimiento.tipo_movimiento = "consumo_labor"

        if commit:
            movimiento.save()
            # Descontar del stock físico del insumo
            insumo = movimiento.insumo
            insumo.stock_actual = max(0, insumo.stock_actual - movimiento.cantidad)
            insumo.save(update_fields=["stock_actual"])

        return movimiento
