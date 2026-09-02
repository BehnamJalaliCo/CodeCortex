import {AuditCenter} from './AuditCenter'
import {BackendCenter} from './BackendCenter'
import {ClusterCenter} from './ClusterCenter'
import {CodeActions} from './CodeActions'
import {IntegrationsCenter} from './IntegrationsCenter'
import {MemoryCenter} from './MemoryCenter'
import {NotificationCenter} from './NotificationCenter'
import {ObservabilityCenter} from './ObservabilityCenter'
import {OrganizationAdmin} from './OrganizationAdmin'
import {PerformanceCenter} from './PerformanceCenter'
import {PlatformManifest} from './PlatformManifest'
import {PRIntelligence} from './PRIntelligence'
import {QualityCenter} from './QualityCenter'

export function PlatformCenters({repositoryId}:{repositoryId:string}){
  return <>
    <PlatformManifest/>
    <PRIntelligence repositoryId={repositoryId}/>
    <QualityCenter repositoryId={repositoryId}/>
    <MemoryCenter repositoryId={repositoryId}/>
    <BackendCenter repositoryId={repositoryId}/>
    <PerformanceCenter repositoryId={repositoryId}/>
    <CodeActions repositoryId={repositoryId}/>
    <IntegrationsCenter repositoryId={repositoryId}/>
    <ClusterCenter/>
    <ObservabilityCenter/>
    <NotificationCenter/>
    <OrganizationAdmin/>
    <AuditCenter/>
  </>
}
