import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

CABECERA = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2" '
    'xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2">\n'
    '<title>Prueba</title><updated>2026-10-30T10:00:00+01:00</updated>\n'
)


def entrada(
    ident, objeto, *, actualizado="2026-10-30T09:00:00.000+01:00", estado="PUB",
    organo="Alcaldía del Ayuntamiento de Sueca", dir3="L01462357", cp="46410", ciudad="Sueca",
    nuts="ES523", cpv="55520000", importe="12000", plazo="2026-11-20", hora="14:00:00",
    procedimiento="9", adjudicatario=None, adjudicado=None, fecha_adj=None, lote=None,
):
    resultado = ""
    if adjudicatario:
        resultado = (
            "<cac:TenderResult><cbc:ResultCode>8</cbc:ResultCode>"
            f"<cbc:AwardDate>{fecha_adj}</cbc:AwardDate>"
            f"<cac:WinningParty><cac:PartyName><cbc:Name>{adjudicatario}</cbc:Name></cac:PartyName></cac:WinningParty>"
            "<cac:AwardedTenderedProject><cac:LegalMonetaryTotal>"
            f'<cbc:TaxExclusiveAmount currencyID="EUR">{adjudicado}</cbc:TaxExclusiveAmount>'
            "</cac:LegalMonetaryTotal></cac:AwardedTenderedProject></cac:TenderResult>"
        )
    lotes = ""
    if lote:
        lotes = (
            "<cac:ProcurementProjectLot><cbc:ID>2</cbc:ID><cac:ProcurementProject>"
            f"<cbc:Name>{lote}</cbc:Name></cac:ProcurementProject></cac:ProcurementProjectLot>"
        )
    plazo_xml = ""
    if plazo:
        plazo_xml = (f"<cac:TenderSubmissionDeadlinePeriod><cbc:EndDate>{plazo}</cbc:EndDate>"
                     f"<cbc:EndTime>{hora}</cbc:EndTime></cac:TenderSubmissionDeadlinePeriod>")
    return f"""
<entry>
 <id>https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/{ident}</id>
 <link href="https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion&amp;idEvl={ident}"/>
 <summary type="text">Id licitación: {ident}; Órgano de Contratación: {organo}</summary>
 <title>{objeto}</title>
 <updated>{actualizado}</updated>
 <cac-place-ext:ContractFolderStatus>
  <cbc:ContractFolderID>EXP-{ident}</cbc:ContractFolderID>
  <cbc-place-ext:ContractFolderStatusCode listURI="x">{estado}</cbc-place-ext:ContractFolderStatusCode>
  <cac-place-ext:LocatedContractingParty>
   <cbc:ContractingPartyTypeCode>3</cbc:ContractingPartyTypeCode>
   <cac:Party>
    <cac:PartyIdentification><cbc:ID schemeName="DIR3">LA0001234</cbc:ID></cac:PartyIdentification>
    <cac:PartyIdentification><cbc:ID schemeName="NIF">P4600000A</cbc:ID></cac:PartyIdentification>
    <cac:PartyName><cbc:Name>{organo}</cbc:Name></cac:PartyName>
    <cac:PostalAddress><cbc:CityName>{ciudad}</cbc:CityName><cbc:PostalZone>{cp}</cbc:PostalZone></cac:PostalAddress>
   </cac:Party>
   <cac-place-ext:ParentLocatedParty>
    <cac:PartyName><cbc:Name>Entidades Locales</cbc:Name></cac:PartyName>
    <cac-place-ext:ParentLocatedParty>
     <cac:PartyIdentification><cbc:ID schemeName="DIR3">{dir3}</cbc:ID></cac:PartyIdentification>
     <cac:PartyName><cbc:Name>Ayuntamiento de {ciudad}</cbc:Name></cac:PartyName>
    </cac-place-ext:ParentLocatedParty>
   </cac-place-ext:ParentLocatedParty>
  </cac-place-ext:LocatedContractingParty>
  <cac:ProcurementProject>
   <cbc:Name>{objeto}</cbc:Name>
   <cbc:TypeCode>2</cbc:TypeCode>
   <cac:BudgetAmount>
    <cbc:EstimatedOverallContractAmount currencyID="EUR">{importe}</cbc:EstimatedOverallContractAmount>
    <cbc:TotalAmount currencyID="EUR">14520</cbc:TotalAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">{importe}</cbc:TaxExclusiveAmount>
   </cac:BudgetAmount>
   <cac:RequiredCommodityClassification><cbc:ItemClassificationCode listURI="x">{cpv}</cbc:ItemClassificationCode></cac:RequiredCommodityClassification>
   <cac:RealizedLocation><cbc:CountrySubentity>Valencia/València</cbc:CountrySubentity><cbc:CountrySubentityCode listURI="x">{nuts}</cbc:CountrySubentityCode></cac:RealizedLocation>
  </cac:ProcurementProject>
  {lotes}
  {resultado}
  <cac:TenderingProcess><cbc:ProcedureCode listURI="x">{procedimiento}</cbc:ProcedureCode>{plazo_xml}</cac:TenderingProcess>
 </cac-place-ext:ContractFolderStatus>
</entry>"""


def feed(*entradas, siguiente=None):
    enlace = f'<link rel="next" href="{siguiente}"/>\n' if siguiente else ""
    return (CABECERA + enlace + "".join(entradas) + "\n</feed>").encode("utf-8")


@pytest.fixture
def config(tmp_path):
    from comun import cargar_config
    return cargar_config(tmp_path / "no_existe.yaml")
