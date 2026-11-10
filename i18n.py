"""Internationalization (i18n): English (default) and Portuguese.

The language is picked from the device's primary locale:
- device language is Portuguese (pt, pt_BR, pt_PT, ...) -> Portuguese
- anything else                                        -> English
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

import flet as ft

from dates import age_in_months

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "pt")

# Locales passed to Flutter so built-in widgets (text selection menu,
# tooltips, dialogs...) also follow the app language.
FLUTTER_LOCALES = {
    "en": ft.Locale("en"),
    "pt": ft.Locale("pt"),
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Common
        "common.back": "Back",
        "common.cancel": "Cancel",
        "common.save": "Save",
        "format.date": "%m/%d/%Y",
        "age.months.one": "{count} month old",
        "age.months.other": "{count} months old",
        "age.years.one": "{count} year old",
        "age.years.other": "{count} years old",
        # Dashboard
        "dashboard.title": "Your classes",
        "dashboard.add_class": "Add new class",
        "dashboard.students_count.one": "{count} child • Tap to manage the students",
        "dashboard.students_count.other": "{count} children • Tap to manage the students",
        "classes.subtitle": "Manage the students or choose the principal class",
        "classes.principal": "Principal",
        "classes.set_default": "Set as principal class",
        "classes.is_default": "Principal class: the app opens on it",
        "classes.default_set": "{name} is now the principal class.",
        "home.no_class_title": "No class yet",
        "home.no_class_message": "Create your first class in Classes (☰ menu).",
        "home.open_classes": "Open classes",
        "menu.home": "Home",
        "menu.classes": "Classes",
        "dashboard.empty_title": "No classes yet",
        "dashboard.empty_message": "Tap “Add new class” to create your first class.",
        # New class form
        "class_form.title": "New class",
        "class_form.name_label": "Class name",
        "class_form.name_hint": "e.g. Preschool II - Afternoon",
        "class_form.color_label": "Color",
        "class_form.error.name_required": "Enter the class name.",
        "class_form.error.name_too_long": "The name is too long.",
        "class_form.error.invalid_color": "Choose a color.",
        "class_form.error.save_failed": "Couldn't save the class. Please try again.",
        # Sign in / create account
        "auth.login_subtitle": "Sign in to open your classes.",
        "auth.register_subtitle": "Create your account to start.",
        "auth.email": "Email",
        "auth.password": "Password",
        "auth.password_hint": "At least {count} characters",
        "auth.confirm_password": "Confirm password",
        "auth.register_notice": (
            "Your data and photos are encrypted on this device and can only be "
            "opened with this password. A forgotten password can't be recovered, "
            "so keep it safe."
        ),
        "auth.sign_in": "Sign in",
        "auth.create_account": "Create account",
        "auth.go_to_register": "Don't have an account? Create one",
        "auth.go_to_login": "Already have an account? Sign in",
        "auth.error.invalid_email": "Enter a valid email address.",
        "auth.error.password_too_short": "The password must have at least 8 characters.",
        "auth.error.password_too_long": "The password is too long.",
        "auth.error.passwords_dont_match": "The passwords don't match.",
        "auth.error.email_taken": "There is already an account with this email on this device.",
        "auth.error.wrong_credentials": "Email or password is incorrect.",
        "auth.error.failed": "Something went wrong. Please try again.",
        "dashboard.sign_out": "Sign out",
        # Reports
        "reports.open_reports": "Reports",
        "reports.title": "Reports",
        "reports.period": "Period",
        "reports.from": "From",
        "reports.to": "To",
        "reports.students": "Students",
        "reports.generate": "Generate reports",
        "reports.privacy": (
            "To write the drafts, the event descriptions and your extra information are "
            "sent to Groq, an AI service outside Brazil. Names are replaced before sending "
            "and photos are never sent. Always review the text before sharing it."
        ),
        "reports.api_key_missing": (
            "To generate reports, add your Groq API key in Settings."
        ),
        "reports.month_group": "{month} {year}",
        "menu.open": "Menu",
        "menu.settings": "Settings",
        "settings.title": "Settings",
        "settings.account": "Account",
        "settings.ai_title": "AI reports (Groq)",
        "settings.api_key": "Groq API key",
        "settings.api_key_help": (
            "Create a key at console.groq.com. It is stored encrypted on this device."
        ),
        "settings.api_key_save": "Save key",
        "settings.api_key_configured": "Groq API key configured",
        "settings.api_key_change": "Change",
        "settings.api_key_remove": "Remove",
        "settings.api_key_saved": "API key saved.",
        "settings.api_key_removed": "API key removed.",
        "settings.api_key_env": (
            "Using GROQ_API_KEY from the environment (development). Save a key here to "
            "replace it."
        ),
        "settings.error.empty_key": "Paste the API key.",
        "reports.error.no_students": "Select at least one student.",
        "reports.error.invalid_period": "The start date must be before the end date.",
        "reports.error.missing_key": "Add your Groq API key in Settings.",
        "reports.instructions": "Instructions for the report (optional)",
        "reports.instructions_hint": (
            "E.g.: Organize in three parts: Interactions, Language and Next steps. Follow "
            "the BNCC fields of experience. Simple language for families."
        ),
        "reports.instructions_help": (
            "The AI follows the structure, standards and tone you write here, but only with "
            "what is in your records. Saved for the next reports."
        ),
        "reports.delete": "Delete report",
        "delete_report.title": "Delete report?",
        "delete_report.message": (
            "The report of {name} ({start} to {end}) will be deleted. This can't be undone. "
            "The events of the learning story are not affected."
        ),
        "delete_report.confirm": "Delete",
        "delete_report.error": "Couldn't delete the report. Please try again.",
        "delete_report.done": "Report deleted.",
        "reports.status.waiting": "Waiting",
        "reports.status.generating": "Writing the report...",
        "reports.status.done": "Report ready",
        "reports.status.no_events": "No events in this period",
        "reports.status.error.missing_key": "Add your Groq API key in Settings.",
        "reports.status.error.invalid_key": "Invalid API key.",
        "reports.status.error.rate_limited": "Too many requests. Wait a minute and try again.",
        "reports.status.error.timeout": "The AI service took too long. Try again.",
        "reports.status.error.network": "No internet connection.",
        "reports.status.error.service": "The AI service had a problem. Try again later.",
        "reports.status.error.empty": "The AI returned an empty text. Try again.",
        "reports.status.error.ungrounded": (
            "The AI text was not based on your records, so it was discarded. Try again."
        ),
        "reports.status.error.model": (
            "The AI model is not available for this API key. Check the models allowed "
            "in your Groq project."
        ),
        "reports.open": "Open",
        "reports.saved_title": "Generated reports",
        "reports.saved_item": "{start} to {end} · generated on {date}",
        "reports.none_yet": "No reports yet.",
        # Report review
        "report_review.title": "Report",
        "report_review.period": "Period: {start} to {end}",
        "report_review.notice": (
            "Draft written by AI from your records. Review and edit it before sharing."
        ),
        "report_review.save_text": "Save text",
        "report_review.generate_pdf": "Generate PDF",
        "report_review.saved": "Report saved.",
        "report_review.save_failed": "Couldn't save the report. Please try again.",
        "report_review.share_pdf": "Share PDF",
        "report_review.pdf_saved": "PDF saved.",
        "report_review.export_failed": "Couldn't create the PDF. Please try again.",
        "report_review.text_required": "The report is empty.",
        "discard_report.title": "Discard changes?",
        "discard_report.message": "Your changes to this report won't be saved.",
        # Report PDF
        "report_pdf.title": "Development and learning report",
        "report_pdf.class": "Class: {name}",
        "report_pdf.age": "Age: {age}",
        "report_pdf.period": "Period: {start} to {end}",
        "report_pdf.issued": "Issued on {date}",
        "report_pdf.signature": "Teacher",
        "report_pdf.photos": "Photo records",
        "report_review.photos_title": "Images in the report",
        "report_review.photos_hint": "They go into the PDF, after the text.",
        "report_review.add_photos": "Add images",
        "report_review.remove_photo": "Remove image",
        "report_review.photo_removed": "Image removed from the report.",
        "report_review.photo_unavailable": "Image not available",
        "report_photos.title": "Choose images",
        "report_photos.hint": (
            "Tap the photos to choose them. They go into the PDF, after the text, in this order."
        ),
        "report_photos.insert": "Insert images ({count})",
        "report_photos.empty_title": "No photos in this period",
        "report_photos.empty_message": "The events of {name} from {start} to {end} have no photos.",
        "report_photos.unsupported": "Not supported in the PDF",
        "report_photos.max": "Up to {count} images per report.",
        "report_photos.inserted.one": "1 image in the report.",
        "report_photos.inserted.other": "{count} images in the report.",
        "report_photos.none": "The report has no images.",
        "report_photos.save_failed": "Couldn't save the images. Please try again.",
        "report_pdf.footer": "RelatórioFácil Infantil · Page {page} of {pages}",
        # Startup
        "startup.db_error_title": "Your data can't be opened",
        "startup.db_error_message": (
            "The encryption key of the local data was not found on this device, "
            "so the saved data can't be read. Nothing was deleted."
        ),
        # Class screen
        "students.count.one": "{count} child",
        "students.count.other": "{count} children",
        "students.hint": "Tap a child to see their learning story.",
        "students.events_count.one": "{count} event",
        "students.events_count.other": "{count} events",
        "students.no_events": "No events yet",
        "students.add_event": "Add event",
        "students.add": "Add student",
        "students.empty_title": "No students yet",
        "students.empty_message": "Add the children of this class in Classes (☰ menu).",
        "students.manage_empty_message": "Tap “Add student” to add the first child to this class.",
        "students.manage_hint": "Tap a child to edit. ⋮ removes them from the class.",
        "students.birth_info": "{age} • Born {date}",
        "students.no_birth_date": "Birth date not set",
        "students.more_options": "More options",
        "students.edit": "Edit",
        "students.remove": "Remove from class",
        "students.transferred_group": "Transferred students ({count})",
        "students.transferred_on": "Transferred on {date}",
        "students.reactivate": "Reactivate",
        "students.reactivated": "{name} is back in the class.",
        "students.reactivate_error": "Couldn't reactivate the student. Please try again.",
        # Student form
        "student_form.add_title": "New student",
        "student_form.edit_title": "Edit student",
        "student_form.name_label": "Full name",
        "student_form.birth_label": "Birth date (optional)",
        "student_form.birth_hint": "Tap to choose",
        "student_form.pick_date": "Choose date",
        "student_form.clear_date": "Clear date",
        "student_form.error.name_required": "Enter the student's name.",
        "student_form.error.name_too_long": "The name is too long.",
        "student_form.error.birth_date_in_future": "The birth date can't be in the future.",
        "student_form.error.invalid_birth_date": "Invalid birth date.",
        "student_form.error.save_failed": "Couldn't save the student. Please try again.",
        # Remove student dialog
        "remove_student.title": "Remove from class?",
        "remove_student.message": (
            "{name} will be listed as transferred in this class. Their data and "
            "learning story are kept, and they can be reactivated at any time."
        ),
        "remove_student.confirm": "Remove",
        "remove_student.error": "Couldn't remove the student. Please try again.",
        # Child screen (learning story)
        "child.story_title": "Learning story",
        "child.empty_title": "No events yet",
        "child.empty_message": (
            "Add photos and comments about significant moments to build "
            "{name}'s learning story."
        ),
        "child.with": "With {names}",
        "child.show_more": "Show older events",
        "child.edit_event": "Edit event",
        "child.extra_info": "Extra information",
        "child.extra_info_hint": (
            "Likes, habits and other things worth knowing about {name}. No date needed."
        ),
        "child.extra_info_placeholder": "e.g. She loves sleeping after lunch.",
        "child.extra_info_saved": "Extra information saved.",
        "child.error.notes_too_long": "The text is too long.",
        "child.error.save_failed": "Couldn't save. Please try again.",
        "child.photo_unavailable": "Photo unavailable",
        # Event form
        "event_form.title": "New event",
        "event_form.edit_title": "Edit event",
        "event_form.photos": "Photos",
        "event_form.take_photo": "Take photo",
        "event_form.gallery": "Gallery",
        "event_form.remove_photo": "Remove photo",
        "event_form.description_label": "What happened?",
        "event_form.description_hint": (
            "Describe the moment and what it shows about the child's growth and learning..."
        ),
        "event_form.date_label": "Date",
        "event_form.children": "Students in this event",
        "event_form.whole_class": "Whole class",
        "event_form.save": "Save event",
        "event_form.error.no_students": "Select at least one child.",
        "event_form.error.unknown_student": (
            "One of the selected children is no longer in this class."
        ),
        "event_form.error.empty": "Add a photo or describe what happened.",
        "event_form.error.description_too_long": "The description is too long.",
        "event_form.error.date_in_future": "The date can't be in the future.",
        "event_form.error.invalid_date": "Invalid date.",
        "event_form.error.too_many_photos": "You can add up to 10 photos.",
        "event_form.error.photo_too_large": "One of the photos is too large.",
        "event_form.error.invalid_photo": "One of the files is not a supported photo.",
        "event_form.error.save_failed": "Couldn't save the event. Please try again.",
        "event_form.error.gallery_failed": "Couldn't open the gallery. Please try again.",
        "event_form.camera_unsupported": (
            "The camera isn't available on this device. Use the gallery to add photos."
        ),
        "event_saved.one": "Event saved to {name}'s learning story.",
        "event_saved.other": "Event saved to the learning stories of {count} students.",
        # Discard event dialog
        "event_updated": "Event updated.",
        "discard_notes.title": "Discard changes?",
        "discard_notes.message": "The text you wrote won't be saved.",
        "discard_changes.title": "Discard changes?",
        "discard_changes.message": "The changes you made to this event will be lost.",
        "discard_event.title": "Discard this event?",
        "discard_event.message": "The photos and text you added will be lost.",
        "discard_event.confirm": "Discard",
        "discard_event.keep": "Keep editing",
        # Camera
        "camera.capture": "Take photo",
        "camera.close": "Close",
        "camera.starting": "Starting the camera...",
        "camera.unavailable": (
            "The camera is not available. Check the camera permission in the phone "
            "settings, or choose a photo from the gallery."
        ),
        "camera.capture_failed": "Couldn't take the photo. Please try again.",
    },
    "pt": {
        # Common
        "common.back": "Voltar",
        "common.cancel": "Cancelar",
        "common.save": "Salvar",
        "format.date": "%d/%m/%Y",
        "age.months.one": "{count} mês",
        "age.months.other": "{count} meses",
        "age.years.one": "{count} ano",
        "age.years.other": "{count} anos",
        # Dashboard
        "dashboard.title": "Suas turmas",
        "dashboard.add_class": "Adicionar nova turma",
        "dashboard.students_count.one": "{count} criança • Toque para gerenciar os alunos",
        "dashboard.students_count.other": "{count} crianças • Toque para gerenciar os alunos",
        "classes.subtitle": "Gerencie os alunos ou escolha a turma principal",
        "classes.principal": "Principal",
        "classes.set_default": "Definir como turma principal",
        "classes.is_default": "Turma principal: o app abre nela",
        "classes.default_set": "{name} agora é a turma principal.",
        "home.no_class_title": "Nenhuma turma ainda",
        "home.no_class_message": "Crie sua primeira turma em Turmas (menu ☰).",
        "home.open_classes": "Abrir turmas",
        "menu.home": "Início",
        "menu.classes": "Turmas",
        "dashboard.empty_title": "Nenhuma turma ainda",
        "dashboard.empty_message": (
            "Toque em “Adicionar nova turma” para criar sua primeira turma."
        ),
        # New class form
        "class_form.title": "Nova turma",
        "class_form.name_label": "Nome da turma",
        "class_form.name_hint": "Ex.: Infantil II - Tarde",
        "class_form.color_label": "Cor",
        "class_form.error.name_required": "Informe o nome da turma.",
        "class_form.error.name_too_long": "O nome está muito longo.",
        "class_form.error.invalid_color": "Escolha uma cor.",
        "class_form.error.save_failed": "Não foi possível salvar a turma. Tente novamente.",
        # Entrar / criar conta
        "auth.login_subtitle": "Entre para abrir suas turmas.",
        "auth.register_subtitle": "Crie sua conta para começar.",
        "auth.email": "E-mail",
        "auth.password": "Senha",
        "auth.password_hint": "Pelo menos {count} caracteres",
        "auth.confirm_password": "Confirme a senha",
        "auth.register_notice": (
            "Seus dados e fotos ficam criptografados neste dispositivo e só podem "
            "ser abertos com esta senha. Uma senha esquecida não pode ser "
            "recuperada, então guarde-a bem."
        ),
        "auth.sign_in": "Entrar",
        "auth.create_account": "Criar conta",
        "auth.go_to_register": "Não tem conta? Crie uma",
        "auth.go_to_login": "Já tem conta? Entre",
        "auth.error.invalid_email": "Informe um e-mail válido.",
        "auth.error.password_too_short": "A senha precisa ter pelo menos 8 caracteres.",
        "auth.error.password_too_long": "A senha é longa demais.",
        "auth.error.passwords_dont_match": "As senhas não conferem.",
        "auth.error.email_taken": "Já existe uma conta com este e-mail neste dispositivo.",
        "auth.error.wrong_credentials": "E-mail ou senha incorretos.",
        "auth.error.failed": "Algo deu errado. Tente novamente.",
        "dashboard.sign_out": "Sair",
        # Relatórios
        "reports.open_reports": "Relatórios",
        "reports.title": "Relatórios",
        "reports.period": "Período",
        "reports.from": "De",
        "reports.to": "Até",
        "reports.students": "Alunos",
        "reports.generate": "Gerar relatórios",
        "reports.privacy": (
            "Para escrever os rascunhos, as descrições dos eventos e suas informações extras "
            "são enviadas ao Groq, um serviço de IA fora do Brasil. Os nomes são trocados "
            "antes do envio e as fotos nunca são enviadas. Sempre revise o texto antes de "
            "compartilhar."
        ),
        "reports.api_key_missing": (
            "Para gerar relatórios, adicione sua chave da API Groq em Configurações."
        ),
        "reports.month_group": "{month} de {year}",
        "menu.open": "Menu",
        "menu.settings": "Configurações",
        "settings.title": "Configurações",
        "settings.account": "Conta",
        "settings.ai_title": "Relatórios com IA (Groq)",
        "settings.api_key": "Chave da API Groq",
        "settings.api_key_help": (
            "Crie uma chave em console.groq.com. Ela fica guardada criptografada neste "
            "dispositivo."
        ),
        "settings.api_key_save": "Salvar chave",
        "settings.api_key_configured": "Chave da API Groq configurada",
        "settings.api_key_change": "Alterar",
        "settings.api_key_remove": "Remover",
        "settings.api_key_saved": "Chave salva.",
        "settings.api_key_removed": "Chave removida.",
        "settings.api_key_env": (
            "Usando a GROQ_API_KEY do ambiente (desenvolvimento). Salve uma chave aqui para "
            "substituí-la."
        ),
        "settings.error.empty_key": "Cole a chave da API.",
        "reports.error.no_students": "Selecione pelo menos um aluno.",
        "reports.error.invalid_period": "A data inicial precisa ser anterior à data final.",
        "reports.error.missing_key": "Adicione sua chave da API Groq em Configurações.",
        "reports.instructions": "Orientações para o relatório (opcional)",
        "reports.instructions_hint": (
            "Ex.: Organize em três partes: Interações, Linguagem e Próximos passos. Siga os "
            "campos de experiência da BNCC. Linguagem simples para as famílias."
        ),
        "reports.instructions_help": (
            "A IA segue a estrutura, os padrões e o tom que você escrever aqui, mas só com o "
            "que está nos seus registros. Fica salvo para os próximos relatórios."
        ),
        "reports.delete": "Excluir relatório",
        "delete_report.title": "Excluir relatório?",
        "delete_report.message": (
            "O relatório de {name} ({start} a {end}) será excluído. Isso não pode ser "
            "desfeito. Os eventos da história de aprendizagem não são afetados."
        ),
        "delete_report.confirm": "Excluir",
        "delete_report.error": "Não foi possível excluir o relatório. Tente novamente.",
        "delete_report.done": "Relatório excluído.",
        "reports.status.waiting": "Aguardando",
        "reports.status.generating": "Escrevendo o relatório...",
        "reports.status.done": "Relatório pronto",
        "reports.status.no_events": "Nenhum evento neste período",
        "reports.status.error.missing_key": (
            "Adicione sua chave da API Groq em Configurações."
        ),
        "reports.status.error.invalid_key": "Chave da API inválida.",
        "reports.status.error.rate_limited": (
            "Muitas solicitações. Aguarde um minuto e tente de novo."
        ),
        "reports.status.error.timeout": "O serviço de IA demorou demais. Tente de novo.",
        "reports.status.error.network": "Sem conexão com a internet.",
        "reports.status.error.service": "O serviço de IA teve um problema. Tente mais tarde.",
        "reports.status.error.empty": "A IA retornou um texto vazio. Tente de novo.",
        "reports.status.error.ungrounded": (
            "O texto da IA não se baseou nos seus registros e foi descartado. Tente de novo."
        ),
        "reports.status.error.model": (
            "O modelo de IA não está disponível para esta chave da API. Verifique os "
            "modelos permitidos no seu projeto Groq."
        ),
        "reports.open": "Abrir",
        "reports.saved_title": "Relatórios gerados",
        "reports.saved_item": "{start} a {end} · gerado em {date}",
        "reports.none_yet": "Nenhum relatório ainda.",
        # Revisão do relatório
        "report_review.title": "Relatório",
        "report_review.period": "Período: {start} a {end}",
        "report_review.notice": (
            "Rascunho escrito por IA a partir dos seus registros. Revise e edite antes de "
            "compartilhar."
        ),
        "report_review.save_text": "Salvar texto",
        "report_review.generate_pdf": "Gerar PDF",
        "report_review.saved": "Relatório salvo.",
        "report_review.save_failed": "Não foi possível salvar o relatório. Tente novamente.",
        "report_review.share_pdf": "Compartilhar PDF",
        "report_review.pdf_saved": "PDF salvo.",
        "report_review.export_failed": "Não foi possível criar o PDF. Tente novamente.",
        "report_review.text_required": "O relatório está vazio.",
        "discard_report.title": "Descartar alterações?",
        "discard_report.message": "Suas alterações neste relatório não serão salvas.",
        # PDF do relatório
        "report_pdf.title": "Relatório de desenvolvimento e aprendizagem",
        "report_pdf.class": "Turma: {name}",
        "report_pdf.age": "Idade: {age}",
        "report_pdf.period": "Período: {start} a {end}",
        "report_pdf.issued": "Emitido em {date}",
        "report_pdf.signature": "Professor(a)",
        "report_pdf.photos": "Registros fotográficos",
        "report_review.photos_title": "Imagens do relatório",
        "report_review.photos_hint": "Elas entram no PDF, depois do texto.",
        "report_review.add_photos": "Adicionar imagens",
        "report_review.remove_photo": "Remover imagem",
        "report_review.photo_removed": "Imagem removida do relatório.",
        "report_review.photo_unavailable": "Imagem indisponível",
        "report_photos.title": "Escolher imagens",
        "report_photos.hint": (
            "Toque nas fotos para escolher. Elas entram no PDF, depois do texto, nesta ordem."
        ),
        "report_photos.insert": "Inserir imagens ({count})",
        "report_photos.empty_title": "Nenhuma foto neste período",
        "report_photos.empty_message": (
            "Os eventos de {name} de {start} a {end} não têm fotos."
        ),
        "report_photos.unsupported": "Formato não aceito no PDF",
        "report_photos.max": "No máximo {count} imagens por relatório.",
        "report_photos.inserted.one": "1 imagem no relatório.",
        "report_photos.inserted.other": "{count} imagens no relatório.",
        "report_photos.none": "O relatório não tem imagens.",
        "report_photos.save_failed": "Não foi possível salvar as imagens. Tente novamente.",
        "report_pdf.footer": "RelatórioFácil Infantil · Página {page} de {pages}",
        # Startup
        "startup.db_error_title": "Não foi possível abrir seus dados",
        "startup.db_error_message": (
            "A chave de criptografia dos dados locais não foi encontrada neste "
            "dispositivo, então os dados salvos não podem ser lidos. Nada foi apagado."
        ),
        # Class screen
        "students.count.one": "{count} criança",
        "students.count.other": "{count} crianças",
        "students.hint": "Toque em uma criança para ver a história de aprendizagem dela.",
        "students.events_count.one": "{count} evento",
        "students.events_count.other": "{count} eventos",
        "students.no_events": "Nenhum evento ainda",
        "students.add_event": "Adicionar evento",
        "students.add": "Adicionar aluno",
        "students.empty_title": "Nenhum aluno ainda",
        "students.empty_message": "Adicione as crianças desta turma em Turmas (menu ☰).",
        "students.manage_empty_message": (
            "Toque em “Adicionar aluno” para incluir a primeira criança nesta turma."
        ),
        "students.manage_hint": "Toque em uma criança para editar. ⋮ remove da turma.",
        "students.birth_info": "{age} • Nasc. {date}",
        "students.no_birth_date": "Data de nascimento não informada",
        "students.more_options": "Mais opções",
        "students.edit": "Editar",
        "students.remove": "Remover da turma",
        "students.transferred_group": "Alunos transferidos ({count})",
        "students.transferred_on": "Transferido(a) em {date}",
        "students.reactivate": "Reativar",
        "students.reactivated": "{name} voltou para a turma.",
        "students.reactivate_error": "Não foi possível reativar o aluno. Tente novamente.",
        # Student form
        "student_form.add_title": "Novo aluno",
        "student_form.edit_title": "Editar aluno",
        "student_form.name_label": "Nome completo",
        "student_form.birth_label": "Data de nascimento (opcional)",
        "student_form.birth_hint": "Toque para escolher",
        "student_form.pick_date": "Escolher data",
        "student_form.clear_date": "Limpar data",
        "student_form.error.name_required": "Informe o nome do aluno.",
        "student_form.error.name_too_long": "O nome está muito longo.",
        "student_form.error.birth_date_in_future": (
            "A data de nascimento não pode ser no futuro."
        ),
        "student_form.error.invalid_birth_date": "Data de nascimento inválida.",
        "student_form.error.save_failed": "Não foi possível salvar o aluno. Tente novamente.",
        # Remove student dialog
        "remove_student.title": "Remover da turma?",
        "remove_student.message": (
            "{name} ficará na lista de transferidos desta turma. Os dados e a história "
            "de aprendizagem são mantidos, e é possível reativar a qualquer momento."
        ),
        "remove_student.confirm": "Remover",
        "remove_student.error": "Não foi possível remover o aluno. Tente novamente.",
        # Child screen (learning story)
        "child.story_title": "História de aprendizagem",
        "child.empty_title": "Nenhum evento ainda",
        "child.empty_message": (
            "Adicione fotos e comentários de momentos significativos para construir "
            "a história de aprendizagem de {name}."
        ),
        "child.with": "Com {names}",
        "child.show_more": "Ver eventos anteriores",
        "child.edit_event": "Editar evento",
        "child.extra_info": "Informações extras",
        "child.extra_info_hint": (
            "Gostos, hábitos e outras informações sobre {name}. Não precisa de data."
        ),
        "child.extra_info_placeholder": "Ex.: Ela adora dormir depois do almoço.",
        "child.extra_info_saved": "Informações extras salvas.",
        "child.error.notes_too_long": "O texto está muito longo.",
        "child.error.save_failed": "Não foi possível salvar. Tente novamente.",
        "child.photo_unavailable": "Foto indisponível",
        # Event form
        "event_form.title": "Novo evento",
        "event_form.edit_title": "Editar evento",
        "event_form.photos": "Fotos",
        "event_form.take_photo": "Tirar foto",
        "event_form.gallery": "Galeria",
        "event_form.remove_photo": "Remover foto",
        "event_form.description_label": "O que aconteceu?",
        "event_form.description_hint": (
            "Descreva o momento e o que ele mostra sobre o desenvolvimento e a "
            "aprendizagem da criança..."
        ),
        "event_form.date_label": "Data",
        "event_form.children": "Alunos neste evento",
        "event_form.whole_class": "Turma",
        "event_form.save": "Salvar evento",
        "event_form.error.no_students": "Selecione pelo menos uma criança.",
        "event_form.error.unknown_student": (
            "Uma das crianças selecionadas não está mais nesta turma."
        ),
        "event_form.error.empty": "Adicione uma foto ou descreva o que aconteceu.",
        "event_form.error.description_too_long": "A descrição está muito longa.",
        "event_form.error.date_in_future": "A data não pode ser no futuro.",
        "event_form.error.invalid_date": "Data inválida.",
        "event_form.error.too_many_photos": "Você pode adicionar até 10 fotos.",
        "event_form.error.photo_too_large": "Uma das fotos é grande demais.",
        "event_form.error.invalid_photo": "Um dos arquivos não é uma foto compatível.",
        "event_form.error.save_failed": "Não foi possível salvar o evento. Tente novamente.",
        "event_form.error.gallery_failed": "Não foi possível abrir a galeria. Tente novamente.",
        "event_form.camera_unsupported": (
            "A câmera não está disponível neste dispositivo. "
            "Use a galeria para adicionar fotos."
        ),
        "event_saved.one": "Evento salvo na história de aprendizagem de {name}.",
        "event_saved.other": "Evento salvo nas histórias de aprendizagem de {count} alunos.",
        # Discard event dialog
        "event_updated": "Evento atualizado.",
        "discard_notes.title": "Descartar alterações?",
        "discard_notes.message": "O texto que você escreveu não será salvo.",
        "discard_changes.title": "Descartar alterações?",
        "discard_changes.message": "As alterações feitas neste evento serão perdidas.",
        "discard_event.title": "Descartar este evento?",
        "discard_event.message": "As fotos e o texto adicionados serão perdidos.",
        "discard_event.confirm": "Descartar",
        "discard_event.keep": "Continuar editando",
        # Camera
        "camera.capture": "Tirar foto",
        "camera.close": "Fechar",
        "camera.starting": "Iniciando a câmera...",
        "camera.unavailable": (
            "A câmera não está disponível. Verifique a permissão da câmera nas "
            "configurações do celular ou escolha uma foto da galeria."
        ),
        "camera.capture_failed": "Não foi possível tirar a foto. Tente novamente.",
    },
}


MONTH_NAMES = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro"],
}


def resolve_language(locales: Sequence[ft.Locale] | None) -> str:
    """Return the app language for the device's locales (primary locale first)."""
    if not locales:
        return DEFAULT_LANGUAGE
    code = (locales[0].language_code or "").replace("-", "_").split("_")[0].lower()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


async def detect_device_language(page: ft.Page) -> str:
    """Read the device locale through Flet; fall back to English on any failure."""
    try:
        info = await page.get_device_info()
    except Exception:  # platform without device info support
        return DEFAULT_LANGUAGE
    return resolve_language(info.locales if info else None)


class Translator:
    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self.language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    @property
    def flutter_locale(self) -> ft.Locale:
        return FLUTTER_LOCALES[self.language]

    def t(self, key: str, **params: Any) -> str:
        text = TRANSLATIONS[self.language].get(key)
        if text is None:
            text = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        return text.format(**params) if params else text

    def plural(self, key: str, count: int, **params: Any) -> str:
        suffix = "one" if count == 1 else "other"
        return self.t(f"{key}.{suffix}", count=count, **params)

    def format_date(self, value: date) -> str:
        return value.strftime(self.t("format.date"))

    def format_month(self, value: date) -> str:
        """"July 2025" / "Julho de 2025" (month names don't depend on the OS locale)."""
        month = MONTH_NAMES[self.language][value.month - 1]
        return self.t("reports.month_group", month=month[0].upper() + month[1:],
                      year=value.year)

    def format_age(self, birth_date: date, today: date | None = None) -> str:
        """'8 months old' under one year, then '3 years old'."""
        months = age_in_months(birth_date, today)
        if months < 12:
            return self.plural("age.months", months)
        return self.plural("age.years", months // 12)
