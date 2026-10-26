import json
import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class WhatsAppCloudService:
    """
    Servicio para integración con la API gratuita de WhatsApp Cloud (Meta for Developers).
    Permite validar webhooks, procesar mensajes de texto y notas de voz de campo (FieldData),
    y enviar respuestas automáticas de confirmación de stock.
    """

    GRAPH_API_VERSION = "v21.0"

    @staticmethod
    def verify_webhook_token(mode: Optional[str], token: Optional[str]) -> bool:
        """
        Valida el desafío GET enviado por Meta para verificar el Webhook.
        Meta envía: hub.mode='subscribe' y hub.verify_token=TU_TOKEN
        """
        expected_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', 'ia_desk_agro_meta_verify_2026')
        return mode == 'subscribe' and token == expected_token

    @classmethod
    def parse_inbound_payload(cls, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extrae datos estructurados de un payload entrante de Meta WhatsApp Cloud API.
        Filtra actualizaciones de estado (delivery receipts) y procesa mensajes reales.
        """
        try:
            entry_list = data.get("entry", [])
            if not entry_list:
                return None

            entry = entry_list[0]
            changes = entry.get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                # Es un evento de estado (enviado, entregado, leído)
                return None

            msg = messages[0]
            contacts = value.get("contacts", [])
            sender_name = "Operario de Campo"
            if contacts:
                sender_name = contacts[0].get("profile", {}).get("name", sender_name)

            from_number = msg.get("from")
            msg_type = msg.get("type", "text")
            msg_id = msg.get("id")

            text_body = ""
            is_audio = False
            audio_id = None

            if msg_type == "text":
                text_body = msg.get("text", {}).get("body", "").strip()
            elif msg_type == "audio" or msg_type == "voice":
                is_audio = True
                audio_id = msg.get("audio", {}).get("id")
                # Si llega un audio sin transcribir por Meta, se registra aviso para el copiloto
                text_body = "[Nota de voz recibida por WhatsApp]"

            return {
                "message_id": msg_id,
                "from_number": from_number,
                "sender_name": sender_name,
                "message_type": msg_type,
                "text_body": text_body,
                "is_audio": is_audio,
                "audio_id": audio_id,
                "metadata": value.get("metadata", {})
            }
        except Exception as e:
            logger.error(f"Error parseando payload de WhatsApp Meta: {e}", exc_info=True)
            return None

    @classmethod
    def send_whatsapp_reply(cls, to_phone: str, message_text: str) -> bool:
        """
        Envía un mensaje de texto de respuesta al número del remitente a través de la API oficial de Meta.
        Usa la capa gratuita de Cloud API (hasta 1.000 conversaciones mensuales sin costo).
        """
        api_token = getattr(settings, 'WHATSAPP_API_TOKEN', '')
        phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')

        if not api_token or not phone_number_id:
            logger.info("WhatsApp Cloud API: Credenciales no configuradas (WHATSAPP_API_TOKEN / WHATSAPP_PHONE_NUMBER_ID). Respuesta simulada.")
            return False

        url = f"https://graph.facebook.com/{cls.GRAPH_API_VERSION}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in [200, 201]:
                logger.info(f"Mensaje de WhatsApp enviado exitosamente a {to_phone}")
                return True
            else:
                logger.warning(f"Fallo envío WhatsApp Meta ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Excepción al enviar WhatsApp Meta a {to_phone}: {e}")
            return False
